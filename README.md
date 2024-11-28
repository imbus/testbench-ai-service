# About
TODO


# Project Structure
```
testbench-ai-proxy
├── doc/                    # Documentation
├── src/                    # Source code
│   ├── main.py             # Main FastAPI application
│   ├── openai_client.py    # Client for OpenAI API interactions
│   └── request_helper.py   # Developer script to run http requests
├── test/                   # (Unit) tests
├── .env                    # Environment variables (OpenAI key); add this yourself
└── requirements.txt        # Project dependencies
```


# Installation
1. Clone the repository.

2. Create a virtual environment and install required packages from requirements.txt.
    ```
    python -m venv testbenchai_venv
    testbenchai_venv\Scripts\activate
    pip install -r requirements.txt
    ```

3. Set up your environment variables: Create a .env file in the project root or set environment variables directly.
    ```
    OPENAI_API_KEY=your_openai_api_key
    ```


# Usage
 
1. Use Uvicorn to start the FastAPI server.
 
    ```
    cd src
    python -m uvicorn main:app --reload
    ```

2. Once the server is running, you can view the interactive API documentation at [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs).

3. Use HTTP requests to access AI services. For example:
   - Endpoint: `POST /generate-test-case-description`
   - Payload:
       ```json
        {
            "test_steps":[
                "Open the application.",
                "Log in with credentials.",
                "Navigate to the account management page.",
                "Delete the account."
            ]
        }
       ```
   - Response:
       ```json
        {
            "description":"This test case involves..."
        }
        ```
