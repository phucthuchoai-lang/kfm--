"""Start the local demonstration platform."""
import os
import uvicorn
from src.web.app import create_app

if __name__ == "__main__":
    uvicorn.run(create_app(), host=os.getenv("HOST", "127.0.0.1"), port=int(os.getenv("PORT", "8000")))
