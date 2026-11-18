/**
 * Pinned, scroll-driven story. One tall track holds a sticky full-screen
 * stage; native scroll position drives the scenes (no scroll hijacking).
 * With reduced motion the same copy renders as a plain, static list.
 */
import { ArrowDown } from 'lucide-react';
import { CompassCore } from './CompassCore';
import { SCENES } from './scenes';
import { SCENE_COUNT, useReducedMotion, useStoryProgress } from './useStoryProgress';

function SceneText({ index }: { index: number }) {
  const s = SCENES[index];
  const Heading = index === 0 ? 'h1' : 'h2';
  return (
    <>
      <p className="story-kicker">{s.kicker}</p>
      <Heading className={index === 0 || index === SCENE_COUNT - 1 ? 'story-title story-title--hero' : 'story-title'}>
        {s.title}
      </Heading>
      <p className="story-text">{s.text}</p>
      {s.chips ? (
        <ul className="story-chips">
          {s.chips.map((c) => <li key={c}>{c}</li>)}
        </ul>
      ) : null}
    </>
  );
}

export function Story() {
  const reduced = useReducedMotion();
  const { trackRef, stageRef } = useStoryProgress(!reduced);

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

        <div className="story-hint" aria-hidden="true">
          <span>Scroll to explore</span>
          <ArrowDown />
        </div>
        <p className="story-note">Conceptual illustration of the routing workflow, not live data.</p>
        <ol className="story-dots" aria-hidden="true">
          {SCENES.map((_, i) => <li key={i} data-i={i} />)}
        </ol>
      </div>
    </section>
  );
}
