import { Composition } from "remotion";
import { FILM_FRAMES, Film } from "./film/Film";
import { ThemeSample } from "./film/ThemeSample";

export const Root: React.FC = () => {
  return (
    <>
      <Composition id="Film" component={Film} durationInFrames={FILM_FRAMES} fps={30} width={1920} height={1080} />
      <Composition id="ThemeSample" component={ThemeSample} durationInFrames={400} fps={30} width={1920} height={1080} />
    </>
  );
};
