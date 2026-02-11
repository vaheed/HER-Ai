from crewai import Crew, Task


class CrewOrchestrator:
    def build_crew(self, agents: dict[str, object]) -> Crew:
        tasks = [
            Task(
                description="Respond to user inputs",
                expected_output="A concise, empathetic reply to the user's latest input.",
                agent=agents["conversation"],
            ),
            Task(
                description="Reflect and extract memories",
                expected_output="A short summary of durable memory candidates from the conversation.",
                agent=agents["reflection"],
            ),
            Task(
                description="Adjust personality traits",
                expected_output="A bounded trait-adjustment recommendation aligned with HER safety rules.",
                agent=agents["personality"],
            ),
        ]

        return Crew(
            agents=[
                agents["conversation"],
                agents["reflection"],
                agents["personality"],
                agents["tool"],
            ],
            tasks=tasks,
            verbose=False,
        )
