#!/usr/bin/env bash
# Usage: render_chunks.sh <scale> <crf> <out.mp4>
# Renders the Film composition in chunks (each retried up to 3 times), renders the audio
# once, then joins video chunks losslessly and muxes the audio.
set -u
SCALE="$1"; CRF="$2"; OUT="$3"
cd "$(dirname "$0")/.."
npx remotion bundle src/index.ts --out-dir build --log=error
TOTAL=$(python -c "import json;T=json.load(open('src/film/vo2.json'));print(round((T[-1]['end']+5.5)*30))")
CHUNK=900
WORK="out/chunks-$SCALE"
mkdir -p "$WORK"
: > "$WORK/list.txt"
start=0
idx=0
while [ $start -lt $TOTAL ]; do
  end=$((start + CHUNK - 1)); [ $end -ge $TOTAL ] && end=$((TOTAL - 1))
  part="$WORK/part$(printf %03d $idx).mp4"
  if [ ! -s "$part" ]; then
    for attempt in 1 2 3; do
      echo "chunk $idx frames $start-$end attempt $attempt"
      if npx remotion render build Film "$part" --frames=$start-$end --muted --scale=$SCALE --codec=h264 --crf=$CRF \
           --timeout=90000 --concurrency=4 --log=error > "$WORK/part$idx.log" 2>&1; then
        break
      fi
      rm -f "$part"
    done
  fi
  [ -s "$part" ] || { echo "FAILED chunk $idx"; exit 1; }
  echo "file 'part$(printf %03d $idx).mp4'" >> "$WORK/list.txt"
  start=$((end + 1)); idx=$((idx + 1))
done
echo "audio"
npx remotion render build Film "$WORK/audio.wav" --codec=wav --log=error > "$WORK/audio.log" 2>&1 || { echo "FAILED audio"; exit 1; }
echo "join"
npx remotion ffmpeg -hide_banner -loglevel error -y -f concat -safe 0 -i "$WORK/list.txt" -i "$WORK/audio.wav" \
  -map 0:v -map 1:a -c:v copy -c:a aac -b:a 192k -movflags +faststart "$OUT" || { echo "FAILED join"; exit 1; }
echo "DONE $OUT"
