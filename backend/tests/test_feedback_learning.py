"""Tests for feedback persistence and adaptive learning pipeline."""
import uuid
import pytest
from app.services import feedback_store
from app.schemas.feedback import FeedbackSubmission


def _uid():
    return f"test-{uuid.uuid4().hex[:8]}"


def _sub(model_id: str, rating: int, thumbs: str = "up") -> FeedbackSubmission:
    return FeedbackSubmission(
        routing_id="r1",
        model_id=model_id,
        model_name=model_id,
        query_summary="test query",
        task_type="reasoning",
        domain="general",
        rating=rating,
        thumbs=thumbs,
        reasons=[],
        comment=None,
    )


class TestFeedbackPersistence:
    def test_submit_returns_record(self):
        uid = _uid()
        rec = feedback_store.submit_feedback(uid, _sub("model-a", 4))
        assert rec.feedback_id
        assert rec.user_id == uid
        assert rec.rating == 4
        assert rec.model_id == "model-a"

    def test_get_user_feedback_returns_submitted(self):
        uid = _uid()
        feedback_store.submit_feedback(uid, _sub("model-a", 5))
        feedback_store.submit_feedback(uid, _sub("model-b", 3))
        records = feedback_store.get_user_feedback(uid)
        assert len(records) == 2

    def test_feedback_isolated_per_user(self):
        uid1, uid2 = _uid(), _uid()
        feedback_store.submit_feedback(uid1, _sub("model-a", 5))
        assert len(feedback_store.get_user_feedback(uid2)) == 0


class TestColdStart:
    def test_cold_start_no_influence(self):
        uid = _uid()
        # 2 ratings — below MIN_SAMPLES_FOR_INFLUENCE=3
        feedback_store.submit_feedback(uid, _sub("model-a", 5))
        feedback_store.submit_feedback(uid, _sub("model-a", 5))
        estimates = feedback_store.get_satisfaction_estimates(uid)
        assert estimates == {}

    def test_cold_start_flag(self):
        uid = _uid()
        state = feedback_store.get_learning_state(uid)
        assert state.cold_start is True
        assert state.learning_active is False

    def test_activates_after_threshold(self):
        uid = _uid()
        for _ in range(3):
            feedback_store.submit_feedback(uid, _sub("model-a", 4))
        state = feedback_store.get_learning_state(uid)
        assert state.learning_active is True
        assert state.cold_start is False


class TestLearningBonuses:
    def test_positive_ratings_give_positive_bonus(self):
        uid = _uid()
        for _ in range(4):
            feedback_store.submit_feedback(uid, _sub("model-good", 5))
        bonus = feedback_store.get_learning_bonus(uid, "model-good")
        assert bonus > 0

    def test_negative_ratings_give_negative_bonus(self):
        uid = _uid()
        for _ in range(4):
            feedback_store.submit_feedback(uid, _sub("model-bad", 1, "down"))
        bonus = feedback_store.get_learning_bonus(uid, "model-bad")
        assert bonus < 0

    def test_neutral_ratings_near_zero(self):
        uid = _uid()
        for _ in range(4):
            feedback_store.submit_feedback(uid, _sub("model-neutral", 3))
        bonus = feedback_store.get_learning_bonus(uid, "model-neutral")
        assert abs(bonus) < 0.02

    def test_bonus_bounded(self):
        uid = _uid()
        for _ in range(25):  # saturate confidence
            feedback_store.submit_feedback(uid, _sub("model-x", 5))
        bonus = feedback_store.get_learning_bonus(uid, "model-x")
        assert bonus <= feedback_store.MAX_LEARNING_BONUS

    def test_unrated_model_zero_bonus(self):
        uid = _uid()
        for _ in range(4):
            feedback_store.submit_feedback(uid, _sub("model-a", 5))
        bonus = feedback_store.get_learning_bonus(uid, "model-unrated")
        assert bonus == 0.0


class TestRoutingIntegration:
    def test_learning_bonus_applied_to_scores(self):
        from app.services.multi_objective_router import route
        from app.services.model_registry import get_all_models
        from app.services.query_analyzer import analyze

        uid = _uid()
        models = get_all_models()
        if not models:
            pytest.skip("No configured models available")

        target = models[0].model_id
        for _ in range(5):
            feedback_store.submit_feedback(uid, _sub(target, 5))

        qp = analyze("Explain neural networks")
        weights = {"quality": 0.3, "cost": 0.2, "latency": 0.15,
                   "reliability": 0.2, "risk": 0.1, "preference_alignment": 0.05}

        d_base = route(models, qp, weights, [], user_id=None)
        d_learn = route(models, qp, weights, [], user_id=uid)

        assert d_learn.learning_active is True
        target_score = next((s for s in d_learn.model_scores if s.model_id == target), None)
        if target_score:
            assert target_score.score_breakdown.get("learning_bonus", 0) > 0

    def test_learning_active_false_without_user(self):
        from app.services.multi_objective_router import route
        from app.services.model_registry import get_all_models
        from app.services.query_analyzer import analyze

        models = get_all_models()
        if not models:
            pytest.skip("No configured models available")
        qp = analyze("test")
        weights = {"quality": 0.3, "cost": 0.2, "latency": 0.15,
                   "reliability": 0.2, "risk": 0.1, "preference_alignment": 0.05}
        d = route(models, qp, weights, [], user_id=None)
        assert d.learning_active is False
