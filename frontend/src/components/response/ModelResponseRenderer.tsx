/**
 * Renders a provider's Markdown response as a document.
 *
 * The provider returns Markdown, so displaying it as plain text is what
 * makes the output look like a copied API payload: the reader sees
 * `###`, `**`, `|` and ``` ``` ``` as literal characters. This component
 * renders the same text as a document while leaving the content itself
 * untouched — no rewriting, no summarising, no truncation.
 *
 * Safety: `react-markdown` builds React elements rather than injecting
 * HTML, and `rehype-raw` is deliberately NOT used, so a response cannot
 * smuggle markup or script through. `skipHtml` drops any raw HTML the
 * model emitted. External links are forced to open safely in a new tab.
 */
import { memo } from 'react';
import ReactMarkdown, { type Components } from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeHighlight from 'rehype-highlight';
import { CodeBlock } from './CodeBlock';
import { MarkdownTable } from './MarkdownTable';

/**
 * Maps the HTML elements `react-markdown` produces onto the components
 * above. Everything not listed here keeps its default rendering, which
 * is correct for `strong`, `em`, `ul`, `ol`, `hr` and friends.
 */
const components: Components = {
  // Fenced blocks, with the fence's language carried through.
  code({ className, children, ...props }) {
    const match = /language-(\w+)/.exec(className ?? '');
    // A fence with no language still arrives as a `code` containing
    // newlines; inline code does not. That is the only reliable
    // distinction, since an unlabelled fence has no `language-` class.
    const isBlock = match !== null || String(children).includes('\n');
    if (!isBlock) {
      return (
        <code className="md-inline-code" {...props}>
          {children}
        </code>
      );
    }
    return <CodeBlock language={match?.[1]}>{children}</CodeBlock>;
  },

  // The table element itself is rendered by MarkdownTable, which owns
  // the wrapper and the class. Passing `props` through here as well
  // would nest a second <table> inside the first.
  table({ children }) {
    return <MarkdownTable>{children}</MarkdownTable>;
  },

  a({ children, href, ...props }) {
    const external = typeof href === 'string' && /^https?:\/\//i.test(href);
    return (
      <a
        href={href}
        {...(external ? { target: '_blank', rel: 'noopener noreferrer' } : {})}
        {...props}
      >
        {children}
      </a>
    );
  },
};

export const ModelResponseRenderer = memo(function ModelResponseRenderer({
  content,
  label,
}: {
  content: string;
  /** Accessible name for the scrollable region. */
  label: string;
}) {
  return (
    <div
      className="model-response"
      role="region"
      aria-label={label}
      tabIndex={0}
    >
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeHighlight]}
        components={components}
        skipHtml
      >
        {content}
      </ReactMarkdown>
    </div>
  );
});
