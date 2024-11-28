from openai import OpenAI
import json

# TODO:
# 1. Determine language of test steps
# 2. Determine length of test
# 3. Generate description
#     in language of test steps
#     with length (max_tokens) appropriate to length of test case

# TODO: Is there a way to elegantly use the same pydantic model for FastAPI data validations and OpenAI's response_format?


class OpenAIClient:
    def __init__(self, api_key: str):
        self.client = OpenAI(api_key=api_key)

    async def generate_test_case_description(self, test_steps: list[str], response_model) -> str:
        """
        Generate a test case description from given test steps.
        """
        # Join the list of steps into a single prompt-friendly format
        test_steps_str = "\n".join(f"- {step}" for step in test_steps)
        print(test_steps_str + "\n\n")

        # Make the OpenAI API call
        completion = self.client.beta.chat.completions.parse(
            messages=[
                {
                    "role": "system",
                    "content": "You are a helpful assistant.",
                },
                {
                    "role": "user",
                    "content": f"Generate a test case description based on the following steps. \n\n Test steps:\n{test_steps_str}",
                    # NOTE: Using "Generate it in the language that the test steps are written in." yields spanish results (most of the time)...
                },
            ],
            model="gpt-4o-2024-08-06",
            max_tokens=200,
            temperature=0,
            response_format=response_model,  # Using structured outputs (JSON schema)
        )

        return json.loads(completion.choices[0].message.content)["description"]
