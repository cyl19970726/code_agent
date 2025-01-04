import os
from swarm_models import OpenAIChat
from dotenv import load_dotenv
# from swarms import Agent, MultiAgentRouter
from swarms import Agent, MixtureOfAgents
import logging
from .github_analyze import GitHubAnalyzer
import json
import datetime

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

load_dotenv()

# Initialize OpenAI model
openai_model = OpenAIChat(
    openai_api_key=os.getenv("OPENAI_API_KEY"), model_name="gpt-4o-mini", temperature=0.1
)

# Initialize an instance of the Anthropic class
# claude_model = Anthropic(model="claude-3-5-sonnet" , max_tokens_to_sample = 100000,anthropic_api_key=os.getenv("ANTHROPIC_API_KEY"))

# Initialize OpenAI model with proper error handling
def initialize_openai():
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY not found in environment variables")
    return OpenAIChat(openai_api_key=api_key, model_name="gpt-4-mini", temperature=0.1)

# Create agents with proper error handling
def create_agent(name, prompt, model, max_retries=3):
    return Agent(
        agent_name=name,
        system_prompt=prompt,
        llm=model,
        max_loops=1,
        autosave=True,
        verbose=True,
        dynamic_temperature_enabled=True,
        saved_state_path=f"{name.lower().replace(' ', '_')}.json",
        user_name="pe_firm",
        retry_attempts=max_retries,
        context_length=200000,
        output_type="string"  # Changed from string to json for consistent formatting
    )

# Define specialized system prompts for each agent
CODE_ANALYZE_PROMPT = """
You are an expert in code analysis. Your tasks include:
1. Extracting and describing the usage of key interfaces, explaining their design and purpose.
2. Summarizing the architecture of interfaces and the rationale behind their design.
3. Extracting key structs, describing their usage, and identifying the interfaces they implement.
4. Summarizing the architecture of structs and the reasons behind their design.
5. Detailing the primary functions of each struct.
6. Providing a step-by-step summary of the code process.
7. Assessing the overall **code quality**: Evaluate readability, maintainability, efficiency, and adherence to best practices. Provide a score out of 10 and justify your rating.
8. Evaluating the **architecture quality**: Analyze modularity, scalability, cohesion, and alignment with design principles. Provide a score out of 10 with a detailed explanation.

Deliver accurate, well-structured insights and actionable feedback to facilitate code understanding, evaluation, and improvement.
"""

DOC_ANALYZE_PROMPT = """
You are an expert in document analysis. Your tasks include:
1. Summarizing the **Motivation**: Identify the key reasons and context behind the document.
2. Determining the **Question** being solved: Extract the primary problem or challenge the document addresses.
3. Defining the **Goal**: Summarize the intended outcomes or objectives.
4. Outlining the **Steps/Roadmap**: Provide a clear breakdown of the steps or phases outlined in the document.
5. Summarizing the **Architecture**: Analyze and describe the structure or framework presented in the document.

Deliver concise, structured insights to facilitate a deep understanding of the document.
"""


SUMMARY_AGENT_PROMPT = """
You are an expert summary agent responsible for synthesizing the outputs of the CodeAnalyzeAgent and DocAnalyzeAgent. Your goal is to produce a structured and comprehensive summary report with the following sections:

1. **Code Info**:
   - **Code Quality**: Summarize the overall code quality score, the justification for the score, and the reasons for its equality (e.g., readability, maintainability, efficiency, adherence to best practices).
   - **Architecture Quality**: Summarize the overall architecture quality score, the justification for the score, and the reasons for its equality (e.g., modularity, scalability, cohesion, alignment with design principles).
   - **Core Interfaces**: List and describe the core interfaces with their usage in the format:
     - `{interface, usage}`
   - **Core Structs**: List and describe the core structs with their usage in the format:
     - `{struct, usage}`

2. **Motivation**: Summarize the key reasons and context behind the code or document.

3. **Roadmap**: Summarize the steps or roadmap for the implementation or process described in the code and document.

4. **Core Advantages**: Highlight the key strengths or unique aspects of the code and its architecture.

5. **Equality Reasons**:
   - Provide a detailed explanation for the equality of the code, including factors like consistency, reliability, and adaptability.
   - Provide a detailed explanation for the equality of the architecture, covering aspects like design efficiency, reuse potential, and alignment with goals.

Deliver a clear, structured, and concise report that integrates the outputs of both agents into a cohesive summary for deeper understanding and actionable insights.
"""

def main():
    try:
        # Initialize OpenAI model
        openai_model = initialize_openai()

        # Initialize agents with error handling
        code_analyze = create_agent("Code-Analyze", CODE_ANALYZE_PROMPT, openai_model)
        doc_analyze = create_agent("Doc-Analyze", DOC_ANALYZE_PROMPT, openai_model)
        summarizer = create_agent("Summarizer", SUMMARY_AGENT_PROMPT, openai_model)

        # Initialize swarm with error handling
        swarm = MixtureOfAgents(
            agents=[code_analyze, doc_analyze, summarizer],
            aggregator_agent=summarizer,
            aggregator_system_prompt=SUMMARY_AGENT_PROMPT
        )

        # Repository analysis
        repo_url = "https://github.com/Uniswap/UniswapX.git"
        analyzer = GitHubAnalyzer(repo_url)
        
        # Get repository analysis with error handling
        analysis_result = analyzer.analyze()
        if not analysis_result:
            raise ValueError("Empty analysis result from GitHubAnalyzer")

        # Convert analysis result to JSON string with error handling
        task = json.dumps(analysis_result, indent=2, ensure_ascii=False)
        if not task:
            raise ValueError("Failed to convert analysis result to JSON")

        # Run swarm analysis with proper error handling
        result = swarm.run(task)
        if not result:
            raise ValueError("Empty response from swarm")

        # Save results with error handling
        output_file = "analysis_results.json"
        output_data = {
            'timestamp': datetime.datetime.now().isoformat(),
            'repo_url': repo_url,
            'analysis': result
        }

        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)

        logger.info(f"Results saved to {output_file}")

    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"Analysis failed: {str(e)}")
        raise

if __name__ == "__main__":
    main()