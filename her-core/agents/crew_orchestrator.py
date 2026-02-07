from crewai import Crew, Task


class CrewOrchestrator:
    def build_crew(self, agents: dict[str, object]) -> Crew:
        tasks = [
            Task(description="Respond to user inputs", agent=agents["conversation"]),
            Task(description="Reflect and extract memories", agent=agents["reflection"]),
            Task(description="Adjust personality traits", agent=agents["personality"]),
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
