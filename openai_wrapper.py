import os
import json
import openai
import logging
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Set OpenAI API key
openai.api_key = os.getenv("OPENAI_API_KEY")

def call_openai_text(prompt: str) -> str:
    """Call OpenAI API with text prompt and return response."""
    try:
        # Ensure prompt is a string
        if isinstance(prompt, dict):
            prompt = json.dumps(prompt)
        
        # Call OpenAI API
        response = openai.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are a helpful assistant that provides responses in valid JSON format."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=100
        )
        
        # Extract response text
        response_text = response.choices[0].message.content
        
        # Log response for debugging
        logger.debug(f"OpenAI Response: {response_text}")
        
        return response_text
        
    except Exception as e:
        logger.error(f"Error calling OpenAI API: {e}")
        raise

if __name__ == '__main__':
    # Test the API
    try:
        result = call_openai_text("Hello, how are you?")
        print(result)
    except Exception as e:
        logger.error("Error in test call: %s", e)
        print("Error:", e)
