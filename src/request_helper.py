import requests

BASE_URL = "http://127.0.0.1:8000"


def run_generate_test_case_description():
    test_steps = [
        "Open the application login page",
        "Enter the username and password",
        "Click on the login button",
        "Verify that the dashboard is displayed",
    ]

    url = f"{BASE_URL}/generate-test-case-description"
    payload = {"test_steps": test_steps}

    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        data = response.json()
        print(data["description"])
    except requests.exceptions.RequestException as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    run_generate_test_case_description()
