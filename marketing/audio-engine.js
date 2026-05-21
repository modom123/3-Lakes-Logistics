// audio-engine.js — multi-style synthesized music + SFX bed.
// All audio is generated procedurally via Web Audio API (no external assets).
//
// Styles:
//   "anthem"   — stadium prime-time-football vibe: 110 BPM minor key, big kick,
//                snare with tail, syncopated brass stabs, tom fills.
//   "driving"  — 125 BPM 4-on-the-floor with sub bass + saw pad (original).
//   "cinematic"— slow 80 BPM, low pulse + pad swells, sparse drum hits.
//   "off"      — silence (still allows VO + SFX).
//
// API:
//   const eng = AudioEngine.create();
//   eng.start();          // user-gesture only
//   eng.stop();
//   eng.setStyle('anthem');
//   eng.setMusicGain(0.6);
//   eng.whoosh(); eng.hit(); eng.swell();

(function () {
  function create() {
    let ctx = null;
    let masterGain, musicGain, sfxGain, musicReverbSend;
    let convolver = null;
    let scheduler = null;
    let running = false;
    let startedAt = 0;
    let nextNoteTime = 0;
    let step = 0;
    let currentStyle = 'anthem';
    const lookahead = 0.05;
    const scheduleAhead = 0.20;

    const mtof = (m) => 440 * Math.pow(2, (m - 69) / 12);

    function init() {
      if (ctx) return;
      ctx = new (window.AudioContext || window.webkitAudioContext)();
      masterGain = ctx.createGain();
      masterGain.gain.value = 0.9;
      masterGain.connect(ctx.destination);

      // Reverb (impulse response synthesized from decaying noise)
      convolver = ctx.createConvolver();
      const irLen = ctx.sampleRate * 1.6;
      const irBuf = ctx.createBuffer(2, irLen, ctx.sampleRate);
      for (let ch = 0; ch < 2; ch++) {
        const d = irBuf.getChannelData(ch);
        for (let i = 0; i < irLen; i++) {
          d[i] = (Math.random() * 2 - 1) * Math.pow(1 - i / irLen, 2.5);
        }
      }
      convolver.buffer = irBuf;
      const reverbOut = ctx.createGain();
      reverbOut.gain.value = 0.35;
      convolver.connect(reverbOut).connect(masterGain);

      musicGain = ctx.createGain();
      musicGain.gain.value = 0;
      musicGain.connect(masterGain);

      musicReverbSend = ctx.createGain();
      musicReverbSend.gain.value = 0.15;
      musicGain.connect(musicReverbSend).connect(convolver);

      sfxGain = ctx.createGain();
      sfxGain.gain.value = 0.85;
      sfxGain.connect(masterGain);
    }

    // ─── Voice generators ───────────────────────────────────────────────────

    // BIG kick with body + click
    function playKick(time, gain = 1.0) {
      // body
      const osc = ctx.createOscillator();
      const g = ctx.createGain();
      osc.frequency.setValueAtTime(160, time);
      osc.frequency.exponentialRampToValueAtTime(42, time + 0.18);
      g.gain.setValueAtTime(gain, time);
      g.gain.exponentialRampToValueAtTime(0.001, time + 0.36);
      osc.connect(g).connect(musicGain);
      osc.start(time); osc.stop(time + 0.4);
      // click
      const buf = ctx.createBuffer(1, ctx.sampleRate * 0.03, ctx.sampleRate);
      const d = buf.getChannelData(0);
      for (let i = 0; i < d.length; i++) d[i] = (Math.random() * 2 - 1) * (1 - i / d.length);
      const s = ctx.createBufferSource();
      s.buffer = buf;
      const hp = ctx.createBiquadFilter();
      hp.type = 'highpass'; hp.frequency.value = 1500;
      const cg = ctx.createGain(); cg.gain.value = gain * 0.35;
      s.connect(hp).connect(cg).connect(musicGain);
      s.start(time);
    }

    function playSnare(time, gain = 0.55, withReverb = true) {
      const dur = 0.22;
      const buf = ctx.createBuffer(1, ctx.sampleRate * dur, ctx.sampleRate);
      const data = buf.getChannelData(0);
      for (let i = 0; i < data.length; i++) data[i] = Math.random() * 2 - 1;
      const src = ctx.createBufferSource();
      src.buffer = buf;
      const bp = ctx.createBiquadFilter();
      bp.type = 'bandpass'; bp.frequency.value = 1700; bp.Q.value = 0.9;
      const g = ctx.createGain();
      g.gain.setValueAtTime(gain, time);
      g.gain.exponentialRampToValueAtTime(0.001, time + dur);
      src.connect(bp).connect(g).connect(musicGain);
      src.start(time);

      const osc = ctx.createOscillator();
      osc.type = 'triangle';
      osc.frequency.setValueAtTime(220, time);
      osc.frequency.exponentialRampToValueAtTime(150, time + 0.08);
      const g2 = ctx.createGain();
      g2.gain.setValueAtTime(gain * 0.5, time);
      g2.gain.exponentialRampToValueAtTime(0.001, time + 0.1);
      osc.connect(g2).connect(musicGain);
      osc.start(time); osc.stop(time + 0.12);

      // Reverb send
      if (withReverb && convolver) {
        const sendGain = ctx.createGain();
        sendGain.gain.value = 0.6;
        bp.connect(sendGain).connect(convolver);
      }
    }

    function playHat(time, open = false, gain = 0.18) {
      const dur = open ? 0.18 : 0.04;
      const buf = ctx.createBuffer(1, ctx.sampleRate * dur, ctx.sampleRate);
      const data = buf.getChannelData(0);
      for (let i = 0; i < data.length; i++) data[i] = Math.random() * 2 - 1;
      const src = ctx.createBufferSource();
      src.buffer = buf;
      const hp = ctx.createBiquadFilter();
      hp.type = 'highpass'; hp.frequency.value = 7500;
      const g = ctx.createGain();
      g.gain.setValueAtTime(gain, time);
      g.gain.exponentialRampToValueAtTime(0.001, time + dur);
      src.connect(hp).connect(g).connect(musicGain);
      src.start(time);
    }

    function playTom(time, pitch = 120, gain = 0.6) {
      const osc = ctx.createOscillator();
      osc.frequency.setValueAtTime(pitch * 1.6, time);
      osc.frequency.exponentialRampToValueAtTime(pitch, time + 0.1);
      const g = ctx.createGain();
      g.gain.setValueAtTime(gain, time);
      g.gain.exponentialRampToValueAtTime(0.001, time + 0.28);
      osc.connect(g).connect(musicGain);
      osc.start(time); osc.stop(time + 0.3);

      // small noise crack
      const buf = ctx.createBuffer(1, ctx.sampleRate * 0.04, ctx.sampleRate);
      const d = buf.getChannelData(0);
      for (let i = 0; i < d.length; i++) d[i] = (Math.random() * 2 - 1) * (1 - i / d.length);
      const s = ctx.createBufferSource();
      s.buffer = buf;
      const hp = ctx.createBiquadFilter();
      hp.type = 'bandpass'; hp.frequency.value = 1200;
      const cg = ctx.createGain(); cg.gain.value = gain * 0.25;
      s.connect(hp).connect(cg).connect(musicGain);
      s.start(time);
    }

    // Punchy brass stab — sawtooth chord through resonant bandpass + fast env
    function playBrassStab(time, notes, gain = 0.42, dur = 0.32) {
      const stabGain = ctx.createGain();
      stabGain.gain.setValueAtTime(0, time);
      stabGain.gain.linearRampToValueAtTime(gain, time + 0.012);
      stabGain.gain.exponentialRampToValueAtTime(0.001, time + dur);

      const bp = ctx.createBiquadFilter();
      bp.type = 'bandpass';
      bp.frequency.setValueAtTime(900, time);
      bp.frequency.exponentialRampToValueAtTime(1600, time + 0.08);
      bp.Q.value = 1.4;
      bp.connect(stabGain).connect(musicGain);

      notes.forEach((n) => {
        const o1 = ctx.createOscillator();
        const o2 = ctx.createOscillator();
        o1.type = 'sawtooth'; o2.type = 'sawtooth';
        o1.frequency.value = mtof(n);
        o2.frequency.value = mtof(n) * 1.005;
        o1.connect(bp); o2.connect(bp);
        o1.start(time); o2.start(time);
        o1.stop(time + dur + 0.05); o2.stop(time + dur + 0.05);
      });

      // Reverb send (small)
      if (convolver) {
        const sendGain = ctx.createGain();
        sendGain.gain.value = 0.3;
        bp.connect(sendGain).connect(convolver);
      }
    }

    function playBass(time, midi, dur, gain = 0.55) {
      const osc = ctx.createOscillator();
      osc.type = 'sawtooth';
      osc.frequency.value = mtof(midi - 24);
      const lp = ctx.createBiquadFilter();
      lp.type = 'lowpass'; lp.frequency.value = 380; lp.Q.value = 4;
      const g = ctx.createGain();
      g.gain.setValueAtTime(0, time);
      g.gain.linearRampToValueAtTime(gain, time + 0.005);
      g.gain.exponentialRampToValueAtTime(0.001, time + dur);
      osc.connect(lp).connect(g).connect(musicGain);
      osc.start(time); osc.stop(time + dur + 0.05);
    }

    function playPadChord(time, notes, dur, gain = 0.13) {
      notes.forEach((n) => {
        const o1 = ctx.createOscillator();
        const o2 = ctx.createOscillator();
        o1.type = 'sawtooth'; o2.type = 'sawtooth';
        o1.frequency.value = mtof(n);
        o2.frequency.value = mtof(n) * 1.005;
        const lp = ctx.createBiquadFilter();
        lp.type = 'lowpass';
        lp.frequency.setValueAtTime(900, time);
        lp.frequency.linearRampToValueAtTime(1600, time + dur * 0.4);
        lp.Q.value = 1.2;
        const g = ctx.createGain();
        g.gain.setValueAtTime(0, time);
        g.gain.linearRampToValueAtTime(gain, time + 0.4);
        g.gain.linearRampToValueAtTime(gain * 0.7, time + dur - 0.3);
        g.gain.linearRampToValueAtTime(0, time + dur);
        o1.connect(lp); o2.connect(lp);
        lp.connect(g).connect(musicGain);
        o1.start(time); o2.start(time);
        o1.stop(time + dur + 0.05); o2.stop(time + dur + 0.05);
      });
    }

    // ─── STYLE PRESETS ──────────────────────────────────────────────────────
    // Each preset declares { bpm, stepsPerBar, schedule(stepIdx, time, elapsed) }.

    // ANTHEM — stadium prime-time vibe. Em → C → G → D, 110 BPM, big drums + brass stabs.
    const STYLE_ANTHEM = (() => {
      const bpm = 110;
      const stepsPerBar = 16; // 16th notes
      const PROG = [
        { name:'Em', root:52, notes:[55, 59, 62] }, // E B (G B E low) — chord tones
        { name:'C',  root:48, notes:[52, 55, 60] },
        { name:'G',  root:43, notes:[50, 55, 59] },
        { name:'D',  root:50, notes:[54, 57, 62] },
      ];

      return {
        bpm, stepsPerBar,
        schedule(stepIdx, time, elapsed) {
          const bar = Math.floor(stepIdx / stepsPerBar);
          const ls = stepIdx % stepsPerBar; // 0..15
          const chord = PROG[bar % PROG.length];
          const stepDur = 60 / bpm / 4;

          // Pad chord — sustained per bar (soft underlay)
          if (ls === 0) {
            playPadChord(time, chord.notes.map(n => n + 12), stepDur * stepsPerBar, 0.10);
          }

          const drumsOn = elapsed > 3.5;
          const stabsOn = elapsed > 5.5;
          const bassOn = elapsed > 5.5;

          if (drumsOn) {
            // Kick: classic stadium rock — 1, 1-and(syncopated), 3, 3-and
            // 16th-note positions: 0, 2 (the &-of-1)…  6 is sometimes added; let's do 0, 6, 8, 14
            if (ls === 0 || ls === 8) playKick(time, 1.0);
            if (ls === 6 || ls === 14) playKick(time, 0.85);
            // Snare: backbeat on 2 and 4 (positions 4 and 12)
            if (ls === 4 || ls === 12) playSnare(time, 0.55, true);
            // Hats every 8th
            if (ls % 2 === 0) playHat(time, false, 0.14);
            // Open hat on offbeat 8ths
            if (ls === 6 || ls === 14) playHat(time, true, 0.10);
          }

          // Brass stabs — anthemic syncopated pattern: hits on beats 1, &-of-2, 3
          // 16th positions: 0, 6, 8
          if (stabsOn) {
            if (ls === 0) playBrassStab(time, chord.notes.map(n => n + 12), 0.45, 0.25);
            if (ls === 6) playBrassStab(time, chord.notes.map(n => n + 12), 0.35, 0.18);
            if (ls === 10) playBrassStab(time, chord.notes.map(n => n + 12), 0.30, 0.16);
          }

          // Bass — root on 1, fifth on &-of-3 (position 10)
          if (bassOn) {
            if (ls === 0) playBass(time, chord.root, stepDur * 4, 0.5);
            if (ls === 8) playBass(time, chord.root, stepDur * 3, 0.45);
            if (ls === 14) playBass(time, chord.root + 7, stepDur * 2, 0.4);
          }

          // Tom fill at the end of bar 4 (every 4-bar phrase) — last beat
          if (drumsOn && (bar % 4 === 3) && ls >= 12) {
            const toms = [180, 150, 120, 95];
            playTom(time, toms[ls - 12], 0.55);
          }
        }
      };
    })();

    // DRIVING — original 125 BPM 4-on-the-floor with sub bass + saw pad.
    const STYLE_DRIVING = (() => {
      const bpm = 125;
      const stepsPerBar = 16;
      const PROG = [
        { root: 57, notes: [60, 64, 69] },
        { root: 53, notes: [60, 65, 69] },
        { root: 60, notes: [60, 64, 67] },
        { root: 55, notes: [59, 62, 67] },
      ];
      return {
        bpm, stepsPerBar,
        schedule(stepIdx, time, elapsed) {
          const stepDur = 60 / bpm / 4;
          const bar = Math.floor(stepIdx / stepsPerBar);
          const ls = stepIdx % stepsPerBar;
          const chord = PROG[bar % PROG.length];

          if (ls === 0) playPadChord(time, chord.notes, stepDur * stepsPerBar, 0.13);

          const drumsOn = elapsed > 4.5;
          if (drumsOn) {
            if (ls % 4 === 0) playKick(time, 0.85);
            if (ls === 4 || ls === 12) playSnare(time, 0.32);
            if (ls % 2 === 0) playHat(time, false, 0.15);
            if (ls % 4 === 2) playHat(time, true, 0.10);
          }

          const bassOn = elapsed > 6.5;
          if (bassOn && ls % 2 === 0) {
            const pattern = [0, 0, 7, 0, 0, 0, 7, 0];
            const eighth = Math.floor(ls / 2);
            playBass(time, chord.root + (pattern[eighth] || 0), stepDur * 1.8, 0.4);
          }
        }
      };
    })();

    // CINEMATIC — slow, sparse. 80 BPM, low pulse + pad swells.
    const STYLE_CINEMATIC = (() => {
      const bpm = 80;
      const stepsPerBar = 16;
      const PROG = [
        { root: 50, notes: [57, 62, 65] },
        { root: 48, notes: [55, 60, 64] },
        { root: 45, notes: [52, 57, 60] },
        { root: 47, notes: [54, 59, 62] },
      ];
      return {
        bpm, stepsPerBar,
        schedule(stepIdx, time, elapsed) {
          const stepDur = 60 / bpm / 4;
          const bar = Math.floor(stepIdx / stepsPerBar);
          const ls = stepIdx % stepsPerBar;
          const chord = PROG[bar % PROG.length];

          if (ls === 0) playPadChord(time, chord.notes, stepDur * stepsPerBar * 1.05, 0.18);

          // Sub pulse on 1 and 3
          if (elapsed > 3 && (ls === 0 || ls === 8)) playBass(time, chord.root - 12, stepDur * 4, 0.35);

          // Sparse snare swell at bar 4 transitions (every 2 bars)
          if (elapsed > 6 && bar % 2 === 1 && ls === 12) playSnare(time, 0.25, true);
        }
      };
    })();

    const STYLES = {
      anthem: STYLE_ANTHEM,
      driving: STYLE_DRIVING,
      cinematic: STYLE_CINEMATIC,
      off: null,
    };

    // ─── Scheduler ──────────────────────────────────────────────────────────
    function getStyle() { return STYLES[currentStyle] || STYLE_ANTHEM; }

    function tick() {
      if (!running) return;
      const style = STYLES[currentStyle];
      if (style) {
        const stepDur = 60 / style.bpm / 4;
        while (nextNoteTime < ctx.currentTime + scheduleAhead) {
          const elapsed = nextNoteTime - startedAt;
          style.schedule(step, nextNoteTime, elapsed);
          nextNoteTime += stepDur;
          step++;
        }
      } else {
        // No-op for 'off' — just advance time
        nextNoteTime = ctx.currentTime + scheduleAhead;
      }
      scheduler = setTimeout(tick, lookahead * 1000);
    }

    // ─── SFX ─────────────────────────────────────────────────────────────────
    function whoosh(direction = 'in') {
      if (!ctx) return;
      const time = ctx.currentTime;
      const dur = 0.35;
      const buf = ctx.createBuffer(1, ctx.sampleRate * dur, ctx.sampleRate);
      const data = buf.getChannelData(0);
      for (let i = 0; i < data.length; i++) data[i] = Math.random() * 2 - 1;
      const src = ctx.createBufferSource();
      src.buffer = buf;
      const bp = ctx.createBiquadFilter();
      bp.type = 'bandpass'; bp.Q.value = 1.2;
      if (direction === 'in') {
        bp.frequency.setValueAtTime(400, time);
        bp.frequency.exponentialRampToValueAtTime(6000, time + dur);
      } else {
        bp.frequency.setValueAtTime(6000, time);
        bp.frequency.exponentialRampToValueAtTime(400, time + dur);
      }
      const g = ctx.createGain();
      g.gain.setValueAtTime(0, time);
      g.gain.linearRampToValueAtTime(0.5, time + 0.05);
      g.gain.exponentialRampToValueAtTime(0.001, time + dur);
      src.connect(bp).connect(g).connect(sfxGain);
      src.start(time);
    }

    function hit() {
      if (!ctx) return;
      const time = ctx.currentTime;
      const osc = ctx.createOscillator();
      osc.frequency.setValueAtTime(170, time);
      osc.frequency.exponentialRampToValueAtTime(38, time + 0.5);
      const g = ctx.createGain();
      g.gain.setValueAtTime(1.0, time);
      g.gain.exponentialRampToValueAtTime(0.001, time + 0.55);
      osc.connect(g).connect(sfxGain);
      osc.start(time); osc.stop(time + 0.6);

      const buf = ctx.createBuffer(1, ctx.sampleRate * 0.15, ctx.sampleRate);
      const d = buf.getChannelData(0);
      for (let i = 0; i < d.length; i++) d[i] = (Math.random() * 2 - 1) * (1 - i / d.length);
      const s = ctx.createBufferSource();
      s.buffer = buf;
      const hp = ctx.createBiquadFilter();
      hp.type = 'highpass'; hp.frequency.value = 1800;
      const g2 = ctx.createGain(); g2.gain.value = 0.4;
      s.connect(hp).connect(g2).connect(sfxGain);
      s.start(time);
    }

    function swell(dur = 1.6) {
      if (!ctx) return;
      const time = ctx.currentTime;
      const buf = ctx.createBuffer(1, ctx.sampleRate * dur, ctx.sampleRate);
      const data = buf.getChannelData(0);
      for (let i = 0; i < data.length; i++) data[i] = Math.random() * 2 - 1;
      const src = ctx.createBufferSource();
      src.buffer = buf;
      const bp = ctx.createBiquadFilter();
      bp.type = 'bandpass'; bp.Q.value = 2;
      bp.frequency.setValueAtTime(200, time);
      bp.frequency.exponentialRampToValueAtTime(5000, time + dur);
      const g = ctx.createGain();
      g.gain.setValueAtTime(0, time);
      g.gain.linearRampToValueAtTime(0.35, time + dur * 0.7);
      g.gain.exponentialRampToValueAtTime(0.001, time + dur);
      src.connect(bp).connect(g).connect(sfxGain);
      src.start(time);
    }

    // ─── Lifecycle ───────────────────────────────────────────────────────────
    function start() {
      init();
      if (running) return;
      if (ctx.state === 'suspended') ctx.resume();
      running = true;
      startedAt = ctx.currentTime + 0.05;
      nextNoteTime = startedAt;
      step = 0;
      musicGain.gain.cancelScheduledValues(ctx.currentTime);
      musicGain.gain.setValueAtTime(0, ctx.currentTime);
      musicGain.gain.linearRampToValueAtTime(0.55, ctx.currentTime + 1.2);
      tick();
    }

    function stop() {
      running = false;
      if (scheduler) { clearTimeout(scheduler); scheduler = null; }
      if (musicGain && ctx) {
        musicGain.gain.cancelScheduledValues(ctx.currentTime);
        musicGain.gain.linearRampToValueAtTime(0, ctx.currentTime + 0.3);
      }
    }

    function setStyle(name) {
      if (!STYLES.hasOwnProperty(name)) return;
      currentStyle = name;
      // Realign step counter to the new style's grid so timing stays sane
      if (ctx && running) {
        const style = STYLES[currentStyle];
        if (style) {
          const stepDur = 60 / style.bpm / 4;
          const elapsed = Math.max(0, ctx.currentTime - startedAt);
          step = Math.floor(elapsed / stepDur);
          nextNoteTime = startedAt + step * stepDur;
        }
      }
    }

    function setMusicGain(v) {
      if (!ctx) return;
      musicGain.gain.linearRampToValueAtTime(v, ctx.currentTime + 0.1);
    }

    function getCtx() { return ctx; }
    function getStyleName() { return currentStyle; }

    return { start, stop, whoosh, hit, swell, setStyle, setMusicGain, getCtx, getStyleName };
  }

  window.AudioEngine = { create };
})();
