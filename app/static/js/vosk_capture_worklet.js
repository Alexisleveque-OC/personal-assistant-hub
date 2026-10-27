// AudioWorklet de capture pour la détection locale du mot-clé (Vosk) :
// regroupe les blocs de 128 échantillons en paquets de ~85 ms (4096 à 48 kHz) envoyés au thread principal.
const CHUNK_SIZE = 4096;

class VoskCaptureProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.buffer = new Float32Array(CHUNK_SIZE);
    this.offset = 0;
  }

  process(inputs) {
    const channel = inputs[0] && inputs[0][0];
    if (!channel) return true;

    let read = 0;
    while (read < channel.length) {
      const count = Math.min(channel.length - read, CHUNK_SIZE - this.offset);
      this.buffer.set(channel.subarray(read, read + count), this.offset);
      this.offset += count;
      read += count;
      if (this.offset === CHUNK_SIZE) {
        this.port.postMessage(this.buffer, [this.buffer.buffer]);
        this.buffer = new Float32Array(CHUNK_SIZE);
        this.offset = 0;
      }
    }
    return true;
  }
}

registerProcessor("vosk-capture", VoskCaptureProcessor);
