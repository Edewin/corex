"""
corex/license.py

Simple license stub for MVP development.
Will be replaced with Polar.sh integration later.
"""

def is_pro() -> bool:
    """Return True if user has Pro tier (MVP: everyone gets Pro during development)."""
    return True  # MVP: everyone gets Pro during development

def get_tier() -> str:
    """Return current license tier: 'free' | 'pro' | 'enterprise'."""
    return "pro"  # MVP: everyone gets Pro during development

def get_max_widget_metrics() -> int:
    """
    Return maximum number of metrics that can be displayed in widget.
    
    Returns:
        int: 999 for Pro (unlimited), 3 for Free tier limit
    """
    if is_pro():
        return 999  # unlimited
    return 3        # free tier limit

def check_feature(feature: str) -> bool:
    """
    Check if a feature is available for current tier.
    
    Args:
        feature: Feature name to check. Valid features:
            'fan_curves', 'alerts', 'history_30d',
            'export', 'plugin_store', 'unlimited_widget'
    
    Returns:
        bool: True if feature is available for current tier
    """
    if is_pro():
        return True
    
    # Free tier features
    free_features = {
        'unlimited_widget': False,
        'fan_curves': False,
        'alerts': False,
        'history_30d': False,
        'export': False,
        'plugin_store': False
    }
    
    return free_features.get(feature, False)