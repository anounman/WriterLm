import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from quality.book_contract import _joined_text, _model_to_dict
from scripts.run_quality_smoke_tests import DOMAINS, create_mock_bundle

payload, plan, request, contract = create_mock_bundle(DOMAINS[0])
text = _joined_text(request, _model_to_dict(plan))
signals = ("code", "programming", "api", "devops", "software", "python", "javascript", "typescript", "cli", "command", "configuration")
for s in signals:
    if s in text:
        print(f"Matched: '{s}'")
