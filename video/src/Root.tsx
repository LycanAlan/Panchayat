import { Composition } from "remotion";
import { EarthZoom } from "./EarthZoom";
import { Explainer } from "./explainer/Explainer";
import { FPS, TOTAL_SECONDS } from "./explainer/core";

export const Root: React.FC = () => {
  return (
    <>
      <Composition
        id="Explainer"
        component={Explainer}
        durationInFrames={Math.round(TOTAL_SECONDS * FPS)}
        fps={FPS}
        width={1920}
        height={1080}
      />
      <Composition
        id="EarthZoom"
        component={EarthZoom}
        durationInFrames={300}
        fps={30}
        width={1920}
        height={1080}
      />
    </>
  );
};
