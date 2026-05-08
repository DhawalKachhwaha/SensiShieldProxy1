import re
LEXICON = {"structure":["article i", "article ii", "section 1.1", "section 2.3", "clause", "hereinafter", "whereas", "hereto", "hereby", "thereof", "therein"],
           "obligation": ["shall", "shall not", "agrees to", "is obligated to", "undertakes to", "covenant", "warrants", "represents"],
           "boilerplate":["termination", "force majeure", "entire agreement", "amendment", "severability", "waiver", "assignment"],
           "legal":["indemnify", "liability", "damages", "governing law", "jurisdiction", "applicable law", "compliance with laws"],
           "strong":["non-disclosure agreement", "nda", "confidential information", "proprietary information", "disclosing party", "receiving party", "mutual agreement", "unilateral agreement", "terms and conditions of this agreement"]}
def score_legal_text(text):
    text_lower = text.lower()
    score = 0

    def count_matches(terms, weight):
        nonlocal score
        for term in terms:
            if term in text_lower:
                score += weight

    count_matches(LEXICON["strong"], 0.6)
    count_matches(LEXICON["structure"], 0.3)
    count_matches(LEXICON["obligation"], 0.2)
    count_matches(LEXICON["legal"], 0.2)
    count_matches(LEXICON["boilerplate"], 0.25)

    # Extra structural boosts
    if re.search(r"\b\d+\.\d+\b", text):
        score += 0.3  # clause numbering

    if text_lower.count("shall") > 3:
        score += 0.3

    return score