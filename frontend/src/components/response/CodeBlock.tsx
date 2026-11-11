/**
 * Fenced code block panel.
 *
 * The provider's raw text arrives as a fenced block; this turns it into a
 * readable panel with a language label and a working copy button. The
 * code itself is passed in already highlighted as React children by
 * `rehype-highlight`, so nothing here parses or escapes the source.
 */
import { useCallback, useRef, useState, type ReactNode } from 'react';
import { Check, Clipboard } from 'lucide-react';

/** Turns a fence's info string into a short, human label. */
function languageLabel(language: string | undefined): string {
  if (!language) return 'Code';
  const cleaned = language.trim().toLowerCase();
  if (!cleaned) return 'Code';
  // Aliases the models use that do not read well as a label.
  const names: Record<string, string> = {
    py: 'Python',
    python: 'Python',
    js: 'JavaScript',
    javascript: 'JavaScript',
    ts: 'TypeScript',
    typescript: 'TypeScript',
    sh: 'Shell',
    bash: 'Shell',
    shell: 'Shell',
    zsh: 'Shell',
    json: 'JSON',
    yaml: 'YAML',
    yml: 'YAML',
    md: 'Markdown',
    markdown: 'Markdown',
    sql: 'SQL',
    rs: 'Rust',
    rust: 'Rust',
    go: 'Go',
    java: 'Java',
    c: 'C',
    cpp: 'C++',
    'c++': 'C++',
    cs: 'C#',
    rb: 'Ruby',
    ruby: 'Ruby',
    php: 'PHP',
    swift: 'Swift',
    kt: 'Kotlin',
    toml: 'TOML',
    ini: 'INI',
    diff: 'Diff',
  };
  return names[cleaned] ?? cleaned.charAt(0).toUpperCase() + cleaned.slice(1);
}

export function CodeBlock({
  language,
  children,
}: {
  language?: string | undefined;
  children: ReactNode;
}) {
  const [copied, setCopied] = useState(false);
  // Scoped to this block: a document-query would copy the first block on
  // the page, which is the wrong code whenever there is more than one.
  const bodyRef = useRef<HTMLPreElement>(null);

  const copy = useCallback(() => {
    const text = bodyRef.current?.innerText ?? '';
    if (!text) return;
    void navigator.clipboard.writeText(text);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1600);
  }, []);

  return (
    <div className="code-block">
      <div className="code-block-header">
        <span className="code-block-language">{languageLabel(language)}</span>
        <button type="button" className="code-block-copy" onClick={copy}>
          {copied ? <Check aria-hidden="true" /> : <Clipboard aria-hidden="true" />}
          {copied ? 'Copied' : 'Copy'}
        </button>
      </div>
      <pre className="code-block-body" ref={bodyRef} tabIndex={0}>
        <code className={`hljs language-${language?.trim().toLowerCase() || 'plaintext'}`}>{children}</code>
      </pre>
    </div>
  );
}
