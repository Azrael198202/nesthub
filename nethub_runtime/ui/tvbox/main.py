# nethub_runtime/ui/tvbox/main.py

from fastapi import FastAPI
import uvicorn

app = FastAPI()


@app.get("/")
def home():
    return {"status": "TV Box UI running"}


def main():
    print("📺 TV Box UI starting at http://127.0.0.1:7788")
    uvicorn.run(app, host="0.0.0.0", port=7788)


if __name__ == "__main__":
    main()