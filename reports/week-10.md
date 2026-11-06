# Semester Week 10 Progress Report

## Completed Work

- Forked the instructor repository and read the README, the level descriptions (`D.md`, `C.md`, `A.md`), the report templates and the repository check scripts.
- Chose the topic: an IELTS Candidate Assistant that answers registration questions (test dates, transfer and cancellation fees, test day rules, results dates) from tool results instead of from the model's memory.
- Chose level C (tool-using agent) and checked the plan against every mandatory C requirement: at least two meaningful tools, LLM tool selection, argument validation, grounded answers, requests without tools, handling of failed tools and missing information, at least eight tests, tool execution logs.
- Wrote `reports/proposal.md` with the problem statement, target users, expected functionality, a specification of 11 functions (name, purpose, inputs, outputs, dependencies), the 4 LLM-callable tools and why the agent needs each of them, the model choice, an architecture diagram, 7 example requests, the evaluation plan and the milestones for weeks 10 to 17.
- Decided on the data: all schedules, fees and policy rules will be mock data written by me for a fictional test centre.

AI assistance: I used Claude (Anthropic) to discuss the scope and to help draft the proposal text. I reviewed every section, changed it where needed and I can explain every decision in it.

## Important Commits

- Week 10 commit: "Add week 10 project proposal and progress report" (`reports/proposal.md`, `reports/week-10.md`). The commit hash is visible in `git log` and in the output of `npm run activity`.

## Current Functionality

No application code yet; week 10 is the planning week. The design is complete on paper: four tools (`find_test_sessions`, `calculate_change_fee`, `search_policy`, `estimate_results_date`), an agent loop with a limit of 6 rounds, argument validation before every tool call, a structured and validated final answer, and a log of every tool call. The repository checks `npm run proposal` and `npm run report -- 10` pass.

## Problems Encountered

1. Real versus mock data. Real IELTS schedules and prices change, and real candidate or company data must never be in a public repository.
2. Choosing the level. Level A gives more points but needs guardrails, permission policies, prompt injection tests and a research paper presentation, which is a lot for the time available.
3. Choosing the language. The starter code of the repository is in Node.js, but I have used Python in all previous homeworks.
4. Scope. There are many possible features (payments, reminders, booking itself), and too many features would make the project hard to finish and test.

## Solutions

1. I will write my own mock data for a fictional centre and clearly mark the rules as simplified, not official. This keeps the repository safe and makes the tests reproducible.
2. I chose level C. It matches what I already practised in HW4 (two tools, a tool-calling loop, argument validation, logs and tests), so I can build it properly and defend every part.
3. I will write the project in Python and keep the starter Node files, so `npm test` and `npm run validate` in CI still work.
4. I limited the agent to answering questions. It does not book, pay or change anything, so there are no risky external actions. Four tools cover the most common questions.

## What I Learned

- A C-level agent must let the model choose the tools; a hard-coded sequence of function calls does not count.
- Grading uses a consistency coefficient, so the work has to be spread over all weeks from 10 to 17 with meaningful commits every week.
- From HW4: the text next to each tool parameter matters a lot for correct tool use, and tools should handle tricky cases in code instead of leaving them to the model. I used both ideas in the tool design.

## Next Week

- Set up the Python environment: `requirements.txt`, `.env.example` with `LLM_API_KEY` and `LLM_MODEL`, check that `.env` is ignored.
- Implement the model adapter `complete(messages, tools)` with the OpenAI client and run the first real request.
- Create the first version of the mock data files (sessions, fees, policy handbook).
- Commit the working code and write the week 11 report.
