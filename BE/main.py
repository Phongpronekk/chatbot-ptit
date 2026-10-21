from fastapi import FastAPI
import uvicorn

app = FastAPI(title="PTIT Chatbot API")


@app.get("/api/health")
def health_check():
    return {"status": "ok"}


if __name__ == "__main__":
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        reload=False
    )
