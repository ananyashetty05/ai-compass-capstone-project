/**
 * Categorised example prompts for the Route Query page.
 *
 * These are only starting points that fill the prompt box; choosing one
 * never changes routing on its own. `taskType` names the existing task
 * type the example most naturally belongs to (used for a small hint).
 */
export interface RouteExample {
  title: string;
  text: string;
}

export interface ExampleCategory {
  id: string;
  label: string;
  /** lucide icon key, resolved in the component. */
  icon: string;
  taskType: string;
  examples: RouteExample[];
}

export const EXAMPLE_CATEGORIES: ExampleCategory[] = [
  {
    id: 'coding', label: 'Coding', icon: 'code', taskType: 'coding',
    examples: [
      { title: 'Longest common subsequence', text: 'Write a Python function that finds the longest common subsequence of two strings and explain its time and space complexity.' },
      { title: 'Rate limiter', text: 'Implement a token-bucket rate limiter in TypeScript with a clean interface and unit tests.' },
      { title: 'CSV to JSON CLI', text: 'Write a small Go command-line tool that converts a CSV file to JSON, streaming rows so large files do not exhaust memory.' },
    ],
  },
  {
    id: 'debugging', label: 'Debugging', icon: 'bug', taskType: 'coding',
    examples: [
      { title: 'Stale React state', text: 'My React component shows an old value inside a setTimeout callback after state updates. Explain why this happens and how to fix it.' },
      { title: 'Intermittent test failure', text: 'A test passes locally but fails intermittently in CI with a timeout. List the most likely causes and how to isolate each one.' },
      { title: 'Memory growth', text: 'A long-running Python service slowly grows in memory. Describe a systematic way to find the leak.' },
    ],
  },
  {
    id: 'research', label: 'Research', icon: 'search', taskType: 'research',
    examples: [
      { title: 'Retrieval vs fine-tuning', text: 'Compare retrieval-augmented generation with fine-tuning for adding domain knowledge to a language model. When is each the better choice?' },
      { title: 'Literature scan', text: 'Give me an overview of the main approaches to model routing and cascading for large language models, and their trade-offs.' },
      { title: 'Technology comparison', text: 'Compare PostgreSQL and MongoDB for an application with relational data and occasional flexible documents.' },
    ],
  },
  {
    id: 'math', label: 'Mathematics', icon: 'sigma', taskType: 'math',
    examples: [
      { title: 'Speed and distance', text: 'A train travels 120 km in 90 minutes. At the same average speed, how long will 400 km take? Show the working.' },
      { title: 'Probability', text: 'Two fair dice are rolled. What is the probability that the sum is at least 9? Explain the counting.' },
      { title: 'Calculus', text: 'Find the derivative of f(x) = x^2 * ln(x) and the x-values where f has a critical point for x > 0.' },
    ],
  },
  {
    id: 'reasoning', label: 'Reasoning', icon: 'brain', taskType: 'reasoning',
    examples: [
      { title: 'Logic puzzle', text: 'Three people each always tell the truth or always lie. A says B lies, B says C lies, C says A and B both lie. Who tells the truth?' },
      { title: 'Trade-off analysis', text: 'Our team can either ship a feature in two weeks with known tech debt or in six weeks cleanly. Lay out the decision criteria and a recommendation.' },
      { title: 'Estimation', text: 'Estimate how many piano tuners work in a city of two million people, stating each assumption.' },
    ],
  },
  {
    id: 'writing', label: 'Writing', icon: 'pen', taskType: 'creative',
    examples: [
      { title: 'Professional email', text: 'Draft a concise, polite email asking a professor for a one-week extension on a project, with a clear reason and a proposed new date.' },
      { title: 'Cover letter', text: 'Write a cover letter opening paragraph for a software engineering internship, emphasising a machine-learning capstone project.' },
      { title: 'Tone rewrite', text: 'Rewrite this paragraph so it sounds confident but not arrogant: "I think maybe I could possibly help with this task if needed."' },
    ],
  },
  {
    id: 'summarization', label: 'Summarization', icon: 'file', taskType: 'summarization',
    examples: [
      { title: 'Meeting notes', text: 'Summarise the following meeting notes into decisions, action items with owners, and open questions: [paste notes here]' },
      { title: 'Article digest', text: 'Summarise the key arguments of the following article in five bullet points and note any claims that lack evidence: [paste article here]' },
      { title: 'Plain-language summary', text: 'Explain the following legal clause in plain language and list what it obliges each party to do: [paste clause here]' },
    ],
  },
  {
    id: 'analysis', label: 'Data analysis', icon: 'chart', taskType: 'analysis',
    examples: [
      { title: 'Interpret results', text: 'A/B test: variant B converted at 5.4% versus 5.0% for A, with 12,000 users each. Is the difference statistically meaningful, and what should we check?' },
      { title: 'SQL query', text: 'Write a SQL query that returns the top three products by revenue per month from orders and order_items tables.' },
      { title: 'Choose a chart', text: 'I have monthly revenue for five regions over two years. Which chart types suit it and what should each highlight?' },
    ],
  },
  {
    id: 'creative', label: 'Creative', icon: 'sparkles', taskType: 'creative',
    examples: [
      { title: 'Short story', text: 'Write a 300-word science-fiction story about a navigation system that refuses to give directions to a place that no longer exists.' },
      { title: 'Product names', text: 'Suggest ten short, memorable names for a study-planner app for engineering students, each with a one-line rationale.' },
      { title: 'Poem', text: 'Write a four-stanza poem about the first monsoon rain in Pune, in a reflective tone.' },
    ],
  },
  {
    id: 'planning', label: 'Planning', icon: 'list', taskType: 'reasoning',
    examples: [
      { title: 'Study plan', text: 'Create a four-week study plan for learning data structures for placements, with about two hours per weekday.' },
      { title: 'Project roadmap', text: 'Break a final-year web application project into milestones for a team of four over twelve weeks, with deliverables for each.' },
      { title: 'Event schedule', text: 'Plan a one-day technical fest schedule with three parallel tracks, lunch, and a closing ceremony.' },
    ],
  },
  {
    id: 'structured', label: 'Structured output', icon: 'braces', taskType: 'coding',
    examples: [
      { title: 'Extract to JSON', text: 'Extract the name, date, and amount from this invoice text and return only valid JSON with those three keys: [paste text here]' },
      { title: 'Markdown table', text: 'Compare REST, GraphQL, and gRPC in a markdown table with columns for typing, performance, tooling, and best use case.' },
      { title: 'Classification', text: 'Classify each of these support tickets as bug, feature request, or question, and return a JSON array of {id, label}: [paste tickets here]' },
    ],
  },
  {
    id: 'explanation', label: 'Technical explanation', icon: 'book', taskType: 'education',
    examples: [
      { title: 'Race conditions', text: 'Explain why a distributed system can experience a race condition and how to prevent it.' },
      { title: 'Learning paradigms', text: 'What are the key differences between supervised and unsupervised learning? Include one example of each.' },
      { title: 'How HTTPS works', text: 'Explain what happens, step by step, when a browser opens an HTTPS page, aimed at a second-year student.' },
    ],
  },
  {
    id: 'architecture', label: 'Software architecture', icon: 'network', taskType: 'coding',
    examples: [
      { title: 'URL shortener', text: 'Design a URL shortening service that handles 100 million links. Cover data model, ID generation, caching, and failure modes.' },
      { title: 'Monolith or services', text: 'We are a team of five building a SaaS product. Should we start with a monolith or microservices? Justify the choice.' },
      { title: 'Real-time chat', text: 'Outline the architecture for a real-time chat feature with message history, read receipts, and offline delivery.' },
    ],
  },
  {
    id: 'multimodal', label: 'Multimodal', icon: 'image', taskType: 'image-generation',
    examples: [
      { title: 'Image prompt', text: 'Generate an illustration of a compass whose needle points to a glowing network of nodes, in a clean flat style.' },
      { title: 'Presentation outline', text: 'Create a ten-slide presentation outline for a capstone project on AI model routing, with speaker notes for each slide.' },
      { title: 'Short video concept', text: 'Create a 20-second product video concept explaining how a query is routed to the best AI model.' },
    ],
  },
];
