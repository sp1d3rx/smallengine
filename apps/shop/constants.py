"""Server-side constants — loaded from data/constants.yaml."""
import os
import yaml

_HERE = os.path.dirname(__file__)
_YAML_PATH = os.path.join(_HERE, "data", "constants.yaml")

with open(_YAML_PATH) as _f:
    _raw = yaml.safe_load(_f)


def _values(key):
    """Return just the value strings for a given key (for pydal IS_IN_SET)."""
    return [item["value"] for item in _raw.get(key, [])]


EQUIPMENT_CATEGORIES = _values("equipment_categories")
SUPPLIER_TERMS       = _values("supplier_terms")
SHIPPING_METHODS     = _values("shipping_methods")

DEFAULT_INTAKE_DISCLAIMER = (
    "1. Diagnostic Fee & Authorization: I authorize the shop to inspect, diagnose, and test-operate the equipment listed above. "
    "A standard diagnostic evaluation fee applies if the repair estimate is declined.\n\n"
    "2. Approval Threshold: Repairs estimated up to the pre-authorized limit or shop approval threshold will proceed automatically. "
    "Any repairs exceeding this amount require customer approval before completion.\n\n"
    "3. Storage & Abandoned Equipment: Equipment must be picked up within 30 calendar days of completion notification. "
    "Items remaining after 30 days are subject to a $5.00/day storage fee. Equipment left unclaimed after 60 days will be "
    "deemed abandoned and disposed of or sold to recover accrued repair and storage costs in accordance with Texas law.\n\n"
    "4. Limited Warranty & Liability: Service labor is guaranteed for 30 days. Replaced parts carry manufacturer warranties. "
    "The shop assumes no liability for loss or damage caused by fire, theft, accidents, or acts of nature beyond reasonable control."
)

# Expose raw data so the API endpoint can serve it directly to Brython.
RAW = _raw
