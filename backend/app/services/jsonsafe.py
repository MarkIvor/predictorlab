import math

import numpy as np


def json_safe(obj):
    if obj is None:
        return None
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, (np.floating,)):
        v = float(obj)
        return v if math.isfinite(v) else None
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if isinstance(obj, np.ndarray):
        return json_safe(obj.tolist())
    if isinstance(obj, dict):
        return {str(k): json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [json_safe(v) for v in obj]
    try:
        import pandas as pd

        if isinstance(obj, (pd.Timestamp,)):
            return obj.isoformat()
        if obj is pd.NaT:
            return None
        if pd.isna(obj):
            return None
    except (TypeError, ValueError):
        return obj
    return obj
