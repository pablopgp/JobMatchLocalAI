"""Static radial indicators requiring no browser chart runtime."""


def compatibility_chart(score=None):
    if score is not None and (
        not isinstance(score, (int, float)) or not 0 <= score <= 100
    ):
        raise ValueError("Compatibility must be between 0 and 100")
    color = (
        "#94a3b8"
        if score is None
        else "#16a34a"
        if score >= 75
        else "#d97706"
        if score >= 45
        else "#dc2626"
    )
    label = f"{score:g}" if score is not None else "Pending"
    subtitle = "/ 100" if score is not None else "Not analyzed"
    progress = score or 0
    size = 34 if score is not None else 20
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="190" height="190" viewBox="0 0 190 190" role="img" aria-label="Compatibility: {label} {subtitle}">
    <title>Compatibility: {label} {subtitle}</title>
    <circle cx="95" cy="95" r="72" fill="none" stroke="#cbd5e1" stroke-width="14"/>
    <circle cx="95" cy="95" r="72" fill="none" stroke="{color}" stroke-width="14" pathLength="100" stroke-dasharray="{progress} 100" transform="rotate(-90 95 95)"/>
    <text x="95" y="93" text-anchor="middle" font-family="Arial, sans-serif" font-size="{size}" font-weight="bold" fill="{color}">{label}</text>
    <text x="95" y="119" text-anchor="middle" font-family="Arial, sans-serif" font-size="14" fill="#94a3b8">{subtitle}</text>
    </svg>'''
