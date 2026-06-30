def detect_remote(title: str, location: str, description: str) -> str:
    text = f"{title} {location} {description}".lower()
    if any(word in text for word in [
        "remote", "work from home", "wfh", "distributed",
        "anywhere in the us", "us only", "fully remote"
    ]):
        return "Yes"
    if any(word in text for word in [
        "on-site", "onsite", "in-office", "in office",
        "hybrid"
    ]):
        return "No/Hybrid"
    return "Unknown"


