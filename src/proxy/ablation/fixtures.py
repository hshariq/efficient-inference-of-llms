"""Shared prompt fixtures for Part 2 coverage tests and Part 4 ablation."""

from __future__ import annotations

# Summarize paraphrases (also in tests/test_tag_coverage — keep in sync or import).
SUMMARIZE_PARAPHRASES = [
    "Please summarize the following in 3 bullets.\n\nDoc A",
    "Summarise this document in three bullet points:\n\nDoc B",
    "I need a summary of this in 3 bullets.\n\nText",
    "Give me a summarized version in three bullets.",
    "Can you provide a summarised overview as bullet points?",
    "Write a short summarization in 3 bullets.",
    "Produce a summarisation with three bullets.",
    "Summary please — 3 bullets only.",
    "Key points in three bullets:\n\n...",
    "Bullet points summary of the text below.",
    "Summarizes the contract in 3 bullets.",
    "Summarizing this report as three bullets.",
    "Summarised findings in bullet points, please.",
    "Give me the summary in three bullets.",
    "3 bullets summarizing the main ideas.",
    "Please do a quick summary (three bullets).",
    "Need bullet-point summary of the following document.",
    "Summarize this agreement into key points.",
]

ENTITY_FOCUS_TEAM = [
    "Summarize the engineering team's progress in 3 bullets.",
    "Key points about our product squad this quarter.",
    "Give me a summary of the department meeting notes.",
    "Three bullets on the organisation's new policy.",
    "Summarise what the group decided yesterday.",
    "Bullet points covering staff feedback themes.",
    "I need a 3-bullet overview of the sales team performance.",
    "Summarize the research team's findings.",
    "Please summarise the board group's discussion.",
    "3 bullets on how the support squad handled incidents.",
    "Summary of the marketing team's campaign results.",
    "Key points from the ops department standup.",
    "Summarize our legal team's contract review.",
    "Three bullets about the design organisation roadmap.",
    "Give a summary of the student group project.",
    "Bullet-point summary of the faculty staff survey.",
]

ENTITY_FOCUS_INDIVIDUAL = [
    "Extract the individual who signed the contract.",
    "Summarize what each person said in 3 bullets.",
    "List named entities: focus on the employee named in clause 2.",
    "Who wrote this memo? Summarize their points in three bullets.",
    "Give me a summary of the author's argument.",
    "Extract entities for each individual mentioned.",
    "3 bullets on what this person claimed.",
    "Summarise the employee's performance review.",
    "Key points from the people interviewed (one individual each).",
    "Find the person who approved the agreement.",
    "Summary of an individual's complaint letter.",
    "Extract entities — especially any author names.",
    "Three bullets describing the person of interest.",
    "Summarize what the individual contributor delivered.",
    "Who signed? Also summarize the letter in 3 bullets.",
    "Bullet summary focused on one person in the case file.",
]

ACTION_ANALYSIS = [
    "Please analyze this report and summarize in 3 bullets.",
    "Compare the two clauses then give key points.",
    "Evaluate the proposal; three bullet summary.",
    "Assess the risk section and summarise.",
    "Review this contract and summarize in bullets.",
    "I need an analysis summary in 3 bullets.",
    "Analyse the quarterly numbers; key points only.",
    "Compare options A and B in three bullets.",
    "Evaluate whether the agreement is fair — summary.",
    "Assess and summarize the findings.",
    "Review then produce a 3-bullet summary.",
    "Provide analysis of the document as bullet points.",
    "Compare last year vs this year; summarize.",
    "Analyse the customer feedback themes.",
    "Evaluate this policy draft in three bullets.",
    "Assess the legal memo and give key points.",
]

ACTION_RETRIEVAL = [
    "Extract all named entities from this document.",
    "Find every organization mentioned below.",
    "List the people named in the contract.",
    "Retrieve the entities from this passage.",
    "Look up entities: people and places only.",
    "Get me all the named entities in the text.",
    "Extract entities from the agreement.",
    "Find locations listed in the report.",
    "List organizations appearing in clause 4.",
    "Retrieve person names from the minutes.",
    "Extract named entities grouped by type.",
    "Find and list every entity in the email.",
    "Get me the entities present in this filing.",
    "Look up who is mentioned in the complaint.",
    "List entities found in the news article.",
    "Extract people, orgs, and locations.",
]

ACTION_GENERATION = [
    "Write web scraping code for this site.",
    "Generate a draft email based on the notes.",
    "Create a short briefing in 3 bullets.",
    "Compose a reply summarizing the issue.",
    "Produce a three-bullet summary of the doc.",
    "Draft a cover letter using these points.",
    "Write a summarized version in bullet points.",
    "Generate bullet points summarizing the text.",
    "Create three bullets that summarize this.",
    "Compose a summary in exactly 3 bullets.",
    "Produce an outline then summarize.",
    "Write code that scrapes product prices.",
    "Draft a summary of the meeting.",
    "Generate a concise 3-bullet digest.",
    "Create documentation summarizing the API.",
    "Write a summary with three bullet points.",
]

# (base_prompt, prompt_with_exclusion, expected_captured_term_substring)
EXCLUSION_PAIRS = [
    (
        "Write web scraping code for this site.",
        "Write web scraping code for this site without BeautifulSoup.",
        "BeautifulSoup",
    ),
    (
        "Generate a scraper for the homepage.",
        "Generate a scraper for the homepage not using Selenium.",
        "Selenium",
    ),
    (
        "Create a parser for the HTML table.",
        "Create a parser for the HTML table excluding pandas.",
        "pandas",
    ),
    (
        "Write a crawler for news pages.",
        "Write a crawler for news pages avoiding Scrapy.",
        "Scrapy",
    ),
    (
        "Draft scraping helpers in Python.",
        "Draft scraping helpers in Python don't use requests.",
        "requests",
    ),
    (
        "Summarize this article in 3 bullets.",
        "Summarize this article in 3 bullets without spoilers.",
        "spoilers",
    ),
    (
        "Extract named entities from the text.",
        "Extract named entities from the text excluding locations.",
        "locations",
    ),
    (
        "Write a summary in three bullets.",
        "Write a summary in three bullets don't include speculation.",
        "speculation",
    ),
]
