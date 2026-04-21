import json
import azure.functions as func

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

VALID_CATEGORIES = {"travel", "meals", "supplies", "equipment", "software", "other"}


@app.route(route="ValidateExpense", methods=["POST"])
def ValidateExpense(req: func.HttpRequest) -> func.HttpResponse:
    try:
        data = req.get_json()
    except ValueError:
        return func.HttpResponse(
            json.dumps({
                "isValid": False,
                "errors": ["Request body must be valid JSON."]
            }),
            status_code=400,
            mimetype="application/json"
        )

    required_fields = [
        "employeeName",
        "employeeEmail",
        "amount",
        "category",
        "description",
        "managerEmail"
    ]

    errors = []

    for field in required_fields:
        value = data.get(field)
        if value is None:
            errors.append(f"Missing required field: {field}")
        elif isinstance(value, str) and not value.strip():
            errors.append(f"Field cannot be empty: {field}")

    category = str(data.get("category", "")).strip().lower()
    if category and category not in VALID_CATEGORIES:
        errors.append(
            "Invalid category. Valid categories: travel, meals, supplies, equipment, software, other."
        )

    amount = data.get("amount")
    try:
        amount_value = float(amount)
        if amount_value < 0:
            errors.append("Amount must be greater than or equal to 0.")
    except (TypeError, ValueError):
        errors.append("Amount must be a valid number.")

    is_valid = len(errors) == 0

    response_body = {
        "isValid": is_valid,
        "errors": errors,
        "normalizedCategory": category if category else None,
        "amount": amount_value if "amount_value" in locals() and is_valid else amount
    }

    return func.HttpResponse(
        json.dumps(response_body),
        status_code=200 if is_valid else 400,
        mimetype="application/json"
    )