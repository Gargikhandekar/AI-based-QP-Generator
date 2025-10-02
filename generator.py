import pandas as pd
from typing import Dict, List, Tuple, Optional


def _coerce_int(value: Optional[str], default: int) -> int:
	try:
		return int(value) if value is not None and str(value).strip() != "" else default
	except ValueError:
		return default


def normalize_mix(raw_mix: Dict[str, float]) -> Dict[str, float]:
	values_sum = sum(max(0.0, float(v)) for v in raw_mix.values())
	if values_sum <= 0:
		# default equal distribution if invalid
		return {"Easy": 0.34, "Medium": 0.33, "Hard": 0.33}
	return {k: max(0.0, float(v)) / values_sum for k, v in raw_mix.items()}


def allocate_questions(
    df: pd.DataFrame,
    subject: Optional[str],
    difficulty_mix: Dict[str, float],
    total_marks: int,
    max_questions: Optional[int] = None,
    prioritize_count: bool = True,
) -> List[Tuple[str, str, int]]:
	"""
	Allocate questions to match total marks and difficulty mix.

	Returns list of (question, topic, marks)
	"""
	if total_marks <= 0:
		return []

	data = df.copy()
	if subject:
		data = data[data["subject"] == subject]

	# Ensure proper types
	data = data.dropna(subset=["question", "topic", "marks", "difficulty"]).copy()
	data["marks"] = pd.to_numeric(data["marks"], errors="coerce").fillna(0).astype(int)

	mix = normalize_mix({
		"Easy": difficulty_mix.get("Easy", 0),
		"Medium": difficulty_mix.get("Medium", 0),
		"Hard": difficulty_mix.get("Hard", 0),
	})

	# Target marks per difficulty bucket
	targets = {k: int(round(total_marks * p)) for k, p in mix.items()}
	# Adjust rounding to match exactly total_marks
	diff_adjust = total_marks - sum(targets.values())
	for k in ["Hard", "Medium", "Easy"]:
		if diff_adjust == 0:
			break
		targets[k] += 1 if diff_adjust > 0 else -1
		diff_adjust += -1 if diff_adjust > 0 else 1

	selected: List[Tuple[str, str, int, str]] = []  # (q, topic, marks, difficulty)
	remaining_marks = total_marks

	# Greedy pick within each bucket by descending marks, then by shorter question text
	for bucket in ["Hard", "Medium", "Easy"]:
		bucket_df = data[data["difficulty"] == bucket].sort_values(
			by=["marks", "question"], ascending=[False, True]
		)
		target = max(0, targets.get(bucket, 0))
		for _, row in bucket_df.iterrows():
			if target <= 0 or remaining_marks <= 0:
				break
			marks = int(row["marks"]) if int(row["marks"]) > 0 else 1
			if marks <= target:
				selected.append((row["question"], row["topic"], marks, bucket))
				target -= marks
				remaining_marks -= marks
				if max_questions is not None and len(selected) >= max_questions:
					break

		if max_questions is not None and len(selected) >= max_questions:
			break

	# If we still have marks left, fill from any remaining questions greedily
	if remaining_marks > 0:
		leftover = data.sort_values(by=["marks"], ascending=[False])
		used = set((q, t, m) for q, t, m, _ in selected)
		for _, row in leftover.iterrows():
			key = (row["question"], row["topic"], int(row["marks"]))
			if key in used:
				continue
			marks = int(row["marks"]) if int(row["marks"]) > 0 else 1
			if marks <= remaining_marks:
				selected.append((row["question"], row["topic"], marks, str(row["difficulty"])) )
				remaining_marks -= marks
				if max_questions is not None and len(selected) >= max_questions:
					break
				if remaining_marks <= 0:
					break

	# If we still did not reach the requested number of questions, optionally relax the marks constraint
	if max_questions is not None and prioritize_count and len(selected) < max_questions:
		# Pick the smallest-mark remaining questions until we hit the count, even if total marks exceed
		leftover_any = data.sort_values(by=["marks"], ascending=[True])
		used_any = set((q, t, m) for q, t, m, _ in selected)
		for _, row in leftover_any.iterrows():
			if len(selected) >= max_questions:
				break
			key = (row["question"], row["topic"], int(row["marks"]))
			if key in used_any:
				continue
			marks = int(row["marks"]) if int(row["marks"]) > 0 else 1
			selected.append((row["question"], row["topic"], marks, str(row["difficulty"])) )

	# Return without difficulty field
	return [(q, t, m) for q, t, m, _ in selected]


