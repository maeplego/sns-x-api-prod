from app.core.embedding_models import EMBEDDING_DIM
from app.embedding.encoder import cosine_similarity, embed_text, mean_embedding


def test_embed_text_is_deterministic():
    first = embed_text("hello world")
    second = embed_text("hello world")
    assert first == second
    assert len(first) == EMBEDDING_DIM


def test_similar_texts_have_high_similarity():
    a = embed_text("python async tutorial for beginners")
    b = embed_text("python async tutorial for beginners")
    assert cosine_similarity(a, b) == 1.0


def test_mean_embedding_averages_vectors():
    vectors = [embed_text("alpha"), embed_text("beta")]
    combined = mean_embedding(vectors)
    assert combined is not None
    assert len(combined) == EMBEDDING_DIM
