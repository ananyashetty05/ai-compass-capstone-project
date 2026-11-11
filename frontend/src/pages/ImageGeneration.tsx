/**
 * Image Generation — placeholder for future integration.
 * Will connect to image-capable models via OpenRouter/OpenAI DALL-E.
 */
import { Image, Sparkles } from 'lucide-react';
import { ButtonLink } from '../components/ui/Button';

export function ImageGeneration() {
  return (
    <div className="page-body">
      <div className="page-header">
        <div className="page-header-text">
          <p className="eyebrow">Create</p>
          <h1 className="page-title">Image Generation</h1>
          <p className="page-description">
            Generate images from text prompts using AI image models.
          </p>
        </div>
      </div>

      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          gap: 'var(--space-4)',
          minHeight: '40vh',
          textAlign: 'center',
          padding: 'var(--space-8)',
          border: '1px dashed var(--color-border)',
          borderRadius: 'var(--radius-xl)',
          background: 'var(--color-surface-muted)',
        }}
      >
        <div
          style={{
            display: 'grid',
            placeItems: 'center',
            width: '3.5rem',
            height: '3.5rem',
            borderRadius: 'var(--radius-xl)',
            background: 'var(--color-primary-subtle)',
            color: 'var(--color-primary)',
          }}
        >
          <Image style={{ width: '1.75rem', height: '1.75rem' }} />
        </div>
        <div>
          <h2 style={{ margin: '0 0 var(--space-2)', fontSize: 'var(--font-size-xl)' }}>
            Coming soon
          </h2>
          <p
            style={{
              margin: 0,
              maxWidth: '40ch',
              color: 'var(--color-text-secondary)',
              fontSize: 'var(--font-size-sm)',
              lineHeight: 'var(--line-height-relaxed)',
            }}
          >
            Image generation will route your prompt to the best available image model —
            DALL-E, Stable Diffusion, or others — through the AI Compass routing engine.
          </p>
        </div>
        <ButtonLink to="/route" variant="primary" leadingIcon={<Sparkles />}>
          Find an image model
        </ButtonLink>
      </div>
    </div>
  );
}
