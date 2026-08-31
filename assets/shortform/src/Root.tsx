import {Composition} from 'remotion';
import {Main} from './Main';
import {GLProbe} from './GLProbe';
import editData from '../public/edit-data.json';

// Composition size/fps/duration come from edit-data.json — set durationSec to
// the exact cut.mp4 duration (ffprobe) when writing the per-video data.
export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition
        id="Reels"
        component={Main}
        durationInFrames={Math.max(1, Math.round(editData.durationSec * editData.fps))}
        fps={editData.fps}
        width={editData.width}
        height={editData.height}
      />
      {/* Diagnostic only — never rendered as a deliverable. Answers "does WebGL
          work in headless render here, and with which --gl backend?".
          See GLProbe.tsx and OPUS-VFX-3D.md § V2. */}
      <Composition
        id="GLProbe"
        component={GLProbe}
        durationInFrames={30}
        fps={30}
        width={540}
        height={960}
      />
    </>
  );
};
