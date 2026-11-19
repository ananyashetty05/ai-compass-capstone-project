/**
 * Pinned, scroll-driven story. One tall track holds a sticky full-screen
 * stage; native scroll position drives the scenes (no scroll hijacking).
 * With reduced motion the same copy renders as a plain, static list.
 */
import { ArrowDown, ArrowRight } from 'lucide-react';
import { CompassCore } from './CompassCore';
import { WarpField } from './WarpField';
import { SCENES } from './scenes';
import { SCENE_COUNT, usePointerParallax, useReducedMotion, useStoryProgress } from './useStoryProgress';

/** Split a title into word spans so each word can surface on its own beat. Whitespace (and line breaks) stay as text. */
function Words({ text }: { text: string }) {
  const parts = text.split(/(\s+)/);
  const count = parts.filter((t) => t.trim()).length;
  let n = 0;
  return (
    <>
      {parts.map((t, k) => {
        if (!t.trim()) return t;
        const i = n++;
        return <span key={k} className="w" style={{ ['--wi' as string]: i, ['--wn' as string]: count }}>{t}</span>;
      })}
    </>
  );
}

function SceneText({ index }: { index: number }) {
  const s = SCENES[index];
  const Heading = index === 0 ? 'h1' : 'h2';
  return (
    <>
      <p className="story-kicker">{s.kicker}</p>
      <Heading className={index === 0 || index === SCENE_COUNT - 1 ? 'story-title story-title--hero' : 'story-title'}>
        <Words text={s.title} />
      </Heading>
      <p className="story-text">{s.text}</p>
      {s.chips ? (
        <ul className="story-chips">
          {s.chips.map((c) => <li key={c}>{c}</li>)}
        </ul>
      ) : null}
      {index === SCENE_COUNT - 1 ? (
        <a className="story-cta" href="#signin">Enter AI Compass <ArrowRight aria-hidden="true" /></a>
      ) : null}
    </>
  );
}

export function Story() {
  const reduced = useReducedMotion();
  const { trackRef, stageRef } = useStoryProgress(!reduced);
  usePointerParallax(stageRef, !reduced);

  /** Native scroll to the middle of a scene; scroll position stays the single source of truth. */
  const jumpTo = (i: number) => {
    const track = trackRef.current;
    if (!track) return;
    const total = track.offsetHeight - window.innerHeight;
    const top = track.getBoundingClientRect().top + window.scrollY + ((i + 0.5) / SCENE_COUNT) * total;
    window.scrollTo({ top, behavior: 'smooth' });
  };

  if (reduced) {
    return (
      <section className="story story--static" aria-label="About AI Compass">
        <div className="story-static-core"><CompassCore className="cc cc--static" /></div>
        {SCENES.map((_, i) => (
          <article key={i} className="story-static-scene">
            <SceneText index={i} />
          </article>
        ))}
        <p className="story-note">Conceptual illustration of the routing workflow, not live data.</p>
      </section>
    );
  }

  return (
    <section className="story" ref={trackRef} aria-label="About AI Compass">
      <div className="story-stage" ref={stageRef} data-scene="0">
        <div className="story-bg" aria-hidden="true" />
        <WarpField />
        <div className="story-spot" aria-hidden="true" />

        <div className="story-core">
          <CompassCore className="cc" />
        </div>

        <div className="story-scenes">
          {SCENES.map((_, i) => (
            <div key={i} className="story-scene" data-i={i} style={{ ['--i' as string]: i }}>
              <SceneText index={i} />
            </div>
          ))}
        </div>

        <div className="story-vignette" aria-hidden="true" />
        <div className="story-hint" aria-hidden="true">
          <span>Scroll to explore</span>
          <ArrowDown />
        </div>
        <p className="story-note">Conceptual illustration of the routing workflow, not live data.</p>
        <nav aria-label="Jump to a story scene">
          <ol className="story-dots">
            {SCENES.map((scene, i) => (
              <li key={i} data-i={i}>
                <button type="button" className="story-dot-btn" aria-label={`Scene ${i + 1} of ${SCENE_COUNT}: ${scene.kicker}`} onClick={() => jumpTo(i)} />
              </li>
            ))}
          </ol>
        </nav>
      </div>
    </section>
  );
}
