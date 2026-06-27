from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    GEMINI_API_KEY: str = ""
    GEMINI_LLM_MODEL: str = "gemini-1.5-flash"
    GEMINI_EMBEDDING_MODEL: str = "models/text-embedding-004"
    CHROMA_PERSIST_DIR: str = "./data/chroma_db"
    UPLOAD_DIR: str = "./data/uploads"
    MAX_FILE_SIZE_MB: int = 10
    CHUNK_SIZE: int = 1000
    CHUNK_OVERLAP: int = 200
    TOP_K_RESULTS: int = 5

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
