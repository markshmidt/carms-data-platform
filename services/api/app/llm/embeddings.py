from langchain_huggingface import HuggingFaceEmbeddings

def get_embeddings():
    return HuggingFaceEmbeddings(
    model_name="intfloat/e5-small-v2",
    model_kwargs={"device": "cpu"},
    )