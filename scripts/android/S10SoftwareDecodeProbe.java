/* SPDX-License-Identifier: GPL-3.0-or-later */
import android.graphics.SurfaceTexture;
import android.media.MediaCodec;
import android.media.MediaCodecInfo;
import android.media.MediaCodecList;
import android.media.MediaExtractor;
import android.media.MediaFormat;
import android.view.Surface;
import java.nio.ByteBuffer;

/** Decode a supplied short fixture with a software codec, including gralloc output. */
public final class S10SoftwareDecodeProbe {
    public static void main(String[] args) throws Exception {
        if (args.length != 2 || !(args[1].equals("buffer") || args[1].equals("surface"))) {
            throw new IllegalArgumentException("Usage: S10SoftwareDecodeProbe <video> <buffer|surface>");
        }
        MediaExtractor extractor = new MediaExtractor();
        MediaCodec codec = null;
        SurfaceTexture texture = null;
        Surface surface = null;
        boolean started = false;
        try {
            extractor.setDataSource(args[0]);
            MediaFormat format = null;
            for (int track = 0; track < extractor.getTrackCount(); track++) {
                MediaFormat candidate = extractor.getTrackFormat(track);
                if (candidate.getString(MediaFormat.KEY_MIME).startsWith("video/")) {
                    extractor.selectTrack(track);
                    format = candidate;
                    break;
                }
            }
            if (format == null) throw new IllegalStateException("No video track");
            String mime = format.getString(MediaFormat.KEY_MIME);
            String name = null;
            for (MediaCodecInfo info : new MediaCodecList(MediaCodecList.ALL_CODECS).getCodecInfos()) {
                if (info.isEncoder() || !info.isSoftwareOnly()) continue;
                for (String type : info.getSupportedTypes()) {
                    if (type.equals(mime)) {
                        name = info.getName();
                        break;
                    }
                }
                if (name != null) break;
            }
            if (name == null) throw new IllegalStateException("No software decoder for " + mime);
            if (args[1].equals("surface")) {
                texture = new SurfaceTexture(false);
                texture.setDefaultBufferSize(format.getInteger(MediaFormat.KEY_WIDTH),
                                             format.getInteger(MediaFormat.KEY_HEIGHT));
                surface = new Surface(texture);
            }
            System.out.println("START codec=" + name + " output=" + args[1]);
            codec = MediaCodec.createByCodecName(name);
            codec.configure(format, surface, null, 0);
            codec.start();
            started = true;
            MediaCodec.BufferInfo info = new MediaCodec.BufferInfo();
            boolean inputEnded = false;
            boolean outputEnded = false;
            int frames = 0;
            long deadline = System.nanoTime() + 10_000_000_000L;
            while (!outputEnded && System.nanoTime() < deadline) {
                if (!inputEnded) {
                    int index = codec.dequeueInputBuffer(10_000);
                    if (index >= 0) {
                        ByteBuffer buffer = codec.getInputBuffer(index);
                        int size = extractor.readSampleData(buffer, 0);
                        if (size < 0) {
                            codec.queueInputBuffer(index, 0, 0, 0, MediaCodec.BUFFER_FLAG_END_OF_STREAM);
                            inputEnded = true;
                        } else {
                            codec.queueInputBuffer(index, 0, size, extractor.getSampleTime(), 0);
                            extractor.advance();
                        }
                    }
                }
                int index = codec.dequeueOutputBuffer(info, 10_000);
                if (index >= 0) {
                    if (info.size > 0) frames++;
                    outputEnded = (info.flags & MediaCodec.BUFFER_FLAG_END_OF_STREAM) != 0;
                    codec.releaseOutputBuffer(index, false);
                }
            }
            if (!outputEnded || frames == 0) {
                throw new IllegalStateException("Decode incomplete: frames=" + frames + " eos=" + outputEnded);
            }
            System.out.println("PASS codec=" + name + " frames=" + frames + " output=" + args[1]);
        } finally {
            if (codec != null) {
                try {
                    if (started) codec.stop();
                } finally {
                    codec.release();
                }
            }
            if (surface != null) surface.release();
            if (texture != null) texture.release();
            extractor.release();
        }
    }
}
