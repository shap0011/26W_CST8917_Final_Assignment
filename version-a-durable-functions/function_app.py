import azure.functions as func
import azure.durable_functions as df
import json
import logging
from datetime import timedelta

app = df.DFApp(http_auth_level=func.AuthLevel.ANONYMOUS)

# ==============================
# 1. HTTP STARTER FUNCTION
# ==============================
@app.route(route="start_expense")
@app.durable_client_input(client_name="client")
async def start_expense_workflow(req: func.HttpRequest, client):
    try:
        data = req.get_json()
    except ValueError:
        return func.HttpResponse("Invalid JSON", status_code=400)

    instance_id = await client.start_new("expense_orchestrator", None, data)

    # return func.HttpResponse(
    #     json.dumps({"instance_id": instance_id}),
    #     mimetype="application/json"
    # )
    
    return client.create_check_status_response(req, instance_id)


# ==============================
# 2. ORCHESTRATOR FUNCTION
# ==============================
@app.orchestration_trigger(context_name="context")
def expense_orchestrator(context: df.DurableOrchestrationContext):
    data = context.get_input() or {}

    # Step 1: Validate
    validation_result = yield context.call_activity("validate_expense", data)

    if not validation_result["is_valid"]:
        result = {
            "status": "validation_error",
            "errors": validation_result["errors"]
        }
        yield context.call_activity("send_notification", result)
        return result

    # Step 2: Check amount
    amount = data.get("amount", 0)

    if amount < 100:
        result = {
            "status": "approved",
            "escalated": False,
            "data": data
        }
        yield context.call_activity("send_notification", result)
        return result

    # Step 3: Wait for manager approval OR timeout
    timeout = context.current_utc_datetime + timedelta(seconds=30)
    timeout_task = context.create_timer(timeout)

    approval_task = context.wait_for_external_event("ManagerDecision")

    winner = yield context.task_any([approval_task, timeout_task])

    if winner == approval_task:
        event_payload = approval_task.result

        if isinstance(event_payload, str):
            try:
                event_payload = json.loads(event_payload)
            except json.JSONDecodeError:
                event_payload = {"decision": event_payload}

        decision = event_payload.get("decision", "approved")

        if decision == "rejected":
            result = {
                "status": "rejected",
                "escalated": False,
                "data": data
            }
        else:
            result = {
                "status": "approved",
                "escalated": False,
                "data": data
            }
    else:
        result = {
            "status": "approved",
            "escalated": True,
            "data": data
        }

    yield context.call_activity("send_notification", result)
    return result


# ==============================
# 3. VALIDATION ACTIVITY
# ==============================
@app.activity_trigger(input_name="expense")
def validate_expense(expense):
    required_fields = [
        "employee_name",
        "employee_email",
        "amount",
        "category",
        "description",
        "manager_email"
    ]

    valid_categories = [
        "travel", "meals", "supplies",
        "equipment", "software", "other"
    ]

    errors = []

    for field in required_fields:
        if field not in expense or expense.get(field) in [None, ""]:
            errors.append(f"Missing {field}")

    if expense.get("category") not in valid_categories:
        errors.append("Invalid category")

    return {
        "is_valid": len(errors) == 0,
        "errors": errors
    }

# ==============================
# 4. NOTIFICATION ACTIVITY
# ==============================
@app.activity_trigger(input_name="notification")
def send_notification(notification):
    logging.info(f"Notification sent: {json.dumps(notification)}")
    return {"sent": True}


# ==============================
# 5. MANAGER APPROVAL ENDPOINT
# ==============================
@app.route(route="manager_approval")
@app.durable_client_input(client_name="client")
async def manager_approval(req: func.HttpRequest, client):
    try:
        body = req.get_json()
        instance_id = body.get("instance_id")
        decision = body.get("decision")
    except:
        return func.HttpResponse("Invalid request", status_code=400)

    await client.raise_event(instance_id, "ManagerDecision", {
        "decision": decision
    })

    return func.HttpResponse("Decision submitted")