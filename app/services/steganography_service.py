"""
Steganography Service - LSB embedding and extraction with Reed-Solomon error correction

Overview of the LSB (Least Significant Bit) technique:
  Each pixel channel in a video frame stores an 8-bit value (0-255).
  The least-significant bit of each value has a negligible visual impact.
  By replacing that bit with one bit of our payload we can hide data
  inside the video without producing perceptible artefacts.

Data flow for embedding:
  plaintext message
      -> AES encrypt (CryptoService)          -> encrypted_bytes
      -> Reed-Solomon encode                  -> protected_bytes (+ ~10% ECC)
      -> prepend 4-byte length header         -> full_payload
      -> convert to bit stream                -> all_bits
      -> LSB-substitute across selected frames -> stego video

Data flow for extraction (reverse):
  stego frames
      -> read LSBs in order                   -> all_bits
      -> parse 4-byte length header
      -> slice data_bits
      -> bits -> bytes                        -> protected_bytes
      -> Reed-Solomon decode + correct errors -> encrypted_bytes
      -> AES decrypt (CryptoService)          -> plaintext message
"""

import numpy as np
from typing import List, Tuple, Optional, Generator, Callable
import reedsolo


class SteganographyService:
    """Service for LSB steganography operations."""

    # Number of Reed-Solomon error-correcting check symbols per block.
    # 10 symbols allow correcting up to 5 symbol errors per block,
    # providing resilience against minor compression artefacts.
    RS_ECC_SYMBOLS = 10

    # Length header size in bits.  A 4-byte (32-bit) big-endian integer
    # is prepended to the payload so the extractor knows exactly how many
    # bytes to read back from the bit stream.  Supports payloads up to ~4 GB.
    LENGTH_HEADER_BITS = 32

    @classmethod
    def data_to_bits(cls, data: bytes) -> Generator[int, None, None]:
        """Convert bytes to a bit generator (MSB first).

        Yields each bit of each byte starting from the most-significant bit
        (bit 7) down to the least-significant bit (bit 0).  MSB-first order
        is the standard network byte order and makes length-header parsing
        straightforward.

        Args:
            data: Bytes to convert

        Yields:
            Individual bits (0 or 1)
        """
        for byte in data:
            for i in range(7, -1, -1):
                yield (byte >> i) & 1

    @classmethod
    def bits_to_bytes(cls, bits: List[int]) -> bytes:
        """Convert a list of bits back to bytes (MSB first).

        Pads the bit list to the next byte boundary with zeros before
        converting.  The caller is responsible for trimming the result
        to the expected length if needed.

        Args:
            bits: List of bits (0 or 1)

        Returns:
            Bytes object reconstructed from the bit list
        """
        # Pad to byte boundary so the loop below always processes full bytes.
        while len(bits) % 8 != 0:
            bits.append(0)

        byte_array = bytearray()
        for i in range(0, len(bits), 8):
            byte = 0
            for j in range(8):
                byte = (byte << 1) | bits[i + j]
            byte_array.append(byte)

        return bytes(byte_array)

    @classmethod
    def apply_error_correction(cls, data: bytes) -> bytes:
        """Apply Reed-Solomon error correction to data.

        Encodes the data into RS codewords by appending ECC check symbols.
        The encoded output is slightly larger than the input (~10% overhead
        for RS_ECC_SYMBOLS=10) but can withstand minor bit-level corruption.

        Args:
            data: Original data bytes

        Returns:
            Data with Reed-Solomon check symbols appended
        """
        n = ecc_symbols if ecc_symbols is not None else cls.RS_ECC_SYMBOLS
        rs = reedsolo.RSCodec(n)
        return bytes(rs.encode(data))

    @classmethod
    def decode_error_correction(cls, data: bytes) -> bytes:
        """Decode and correct errors using Reed-Solomon.

        Attempts to decode the RS-encoded data and correct any symbol
        errors introduced by video compression or transmission noise.
        Raises ValueError if the errors exceed the correctable threshold.

        Args:
            data: Data with Reed-Solomon check symbols

        Returns:
            Corrected original data (without the ECC symbols)
        """
        n = ecc_symbols if ecc_symbols is not None else cls.RS_ECC_SYMBOLS
        rs = reedsolo.RSCodec(n)
        try:
            decoded = rs.decode(data)
            # rs.decode returns a tuple (decoded_msg, decoded_msgecc, errata_pos)
            # in newer versions of the library; handle both tuple and bytes.
            return bytes(decoded[0]) if isinstance(decoded, tuple) else bytes(decoded)
        except reedsolo.ReedSolomonError as e:
            raise ValueError(f"Error correction failed: {e}")

    @classmethod
    def embed_in_frame(cls, frame: np.ndarray,
                       data_bits: List[int],
                       bit_position: int = 0,
                       regions: Optional[List[dict]] = None,
                       channel_mode: str = 'rgb') -> Tuple[np.ndarray, int]:
        """Embed data bits into a single frame using LSB substitution.

        For each target pixel channel value, the bit at `bit_position`
        is replaced with the next bit from `data_bits`.  bit_position=0
        modifies the LSB (least visual impact); bit_position=1 modifies
        the 2nd LSB (more robust against re-encoding but slightly more
        visible).

        Embedding modes:
          - 'rgb'  : embed into all three BGR channels sequentially
          - 'luma' : convert frame to YCrCb, embed only into the Y (luma)
                     channel, then convert back.  Luma embedding is more
                     robust against chroma subsampling used by social media.

        Region-aware embedding:
          When `regions` is provided (from AIService.analyze_frame_for_embedding),
          bits are embedded only within those high-texture blocks.  This
          concentrates the payload in areas where statistical anomalies
          are harder to detect.

        Args:
            frame: Video frame as a (H, W, 3) uint8 numpy array
            data_bits: List of bits to embed (stops when the list is exhausted)
            bit_position: Which bit position to modify (0 = LSB)
            regions: Optional list of {'x', 'y', 'width', 'height'} dicts
            channel_mode: 'rgb' or 'luma'

        Returns:
            Tuple of (modified frame as uint8 array, number of bits embedded)
        """
        if channel_mode not in ('rgb', 'luma'):
            raise ValueError("channel_mode must be 'rgb' or 'luma'")

        work_frame = frame.copy()

        # Use a stable stored channel for luma-style embedding. BGR<->YCrCb
        # round-trips are not bit-exact and corrupt LSB payloads.
        if channel_mode == 'luma':
            plane = work_frame[:, :, 1]
        else:
            plane = None

        bits_embedded = 0
        bit_iter = iter(data_bits)

        def set_bit(value: int, bit: int) -> int:
            """Replace the target bit position in `value` with `bit`."""
            mask = ~(1 << bit_position)
            return (value & mask) | (bit << bit_position)

        if regions:
            # Content-aware path: iterate only over the specified rectangular
            # regions so hidden bits are concentrated in high-texture areas.
            for region in regions:
                x0 = int(region.get('x', 0))
                y0 = int(region.get('y', 0))
                w = int(region.get('width', 0))
                h = int(region.get('height', 0))

                if w <= 0 or h <= 0:
                    continue

                # Clamp coordinates to frame dimensions to avoid index errors.
                y1 = min(y0 + h, work_frame.shape[0])
                x1 = min(x0 + w, work_frame.shape[1])
                y0 = max(0, y0)
                x0 = max(0, x0)

                for y in range(y0, y1):
                    for x in range(x0, x1):
                        if channel_mode == 'luma':
                            try:
                                bit = next(bit_iter)
                            except StopIteration:
                                return work_frame.astype(np.uint8), bits_embedded
                            plane[y, x] = set_bit(int(plane[y, x]), bit)
                            bits_embedded += 1
                        else:
                            for c in range(3):
                                try:
                                    bit = next(bit_iter)
                                except StopIteration:
                                    return work_frame.astype(np.uint8), bits_embedded
                                work_frame[y, x, c] = set_bit(int(work_frame[y, x, c]), bit)
                                bits_embedded += 1
        else:
            # Default sequential path: flatten the channel array and embed
            # bits one-by-one across every pixel in raster order.
            if channel_mode == 'luma':
                flat = plane.flatten()
                for i in range(len(flat)):
                    try:
                        bit = next(bit_iter)
                    except StopIteration:
                        break
                    flat[i] = set_bit(int(flat[i]), bit)
                    bits_embedded += 1
                plane = flat.reshape(plane.shape)
            else:
                flat = work_frame.flatten()
                for i in range(len(flat)):
                    try:
                        bit = next(bit_iter)
                    except StopIteration:
                        break
                    flat[i] = set_bit(int(flat[i]), bit)
                    bits_embedded += 1
                work_frame = flat.reshape(work_frame.shape)

        # Write the modified luma plane back into the YCrCb image and
        # convert back to BGR so the rest of the pipeline works normally.
        if channel_mode == 'luma':
            work_frame[:, :, 1] = plane

        return work_frame.astype(np.uint8), bits_embedded

    @classmethod
    def extract_from_frame(cls, frame: np.ndarray,
                          num_bits: int,
                          bit_position: int = 0,
                          regions: Optional[List[dict]] = None,
                          channel_mode: str = 'rgb') -> List[int]:
        """Extract data bits from a single frame using LSB reading.

        Mirrors embed_in_frame exactly: it reads the same bit position
        from the same channels/regions in the same pixel order so the
        extracted bit stream matches what was embedded.

        Args:
            frame: Video frame as a (H, W, 3) uint8 numpy array
            num_bits: Maximum number of bits to extract
            bit_position: Which bit position to read (must match embedding)
            regions: Optional list of region dicts (must match embedding)
            channel_mode: 'rgb' or 'luma' (must match embedding)

        Returns:
            List of extracted bits (length <= num_bits)
        """
        if channel_mode not in ('rgb', 'luma'):
            raise ValueError("channel_mode must be 'rgb' or 'luma'")

        extracted_bits: List[int] = []

        # Convert to YCrCb and extract the luma plane if needed.
        if channel_mode == 'luma':
            plane = frame[:, :, 1]
        else:
            plane = None

        def get_bit(value: int) -> int:
            """Extract the bit at bit_position from value."""
            return (value >> bit_position) & 1

        if regions:
            # Region-aware extraction: match the same bounding boxes used
            # during embedding.
            for region in regions:
                x0 = int(region.get('x', 0))
                y0 = int(region.get('y', 0))
                w = int(region.get('width', 0))
                h = int(region.get('height', 0))

                if w <= 0 or h <= 0:
                    continue

                y1 = min(y0 + h, frame.shape[0])
                x1 = min(x0 + w, frame.shape[1])
                y0 = max(0, y0)
                x0 = max(0, x0)

                for y in range(y0, y1):
                    for x in range(x0, x1):
                        if len(extracted_bits) >= num_bits:
                            return extracted_bits
                        if channel_mode == 'luma':
                            extracted_bits.append(get_bit(int(plane[y, x])))
                        else:
                            for c in range(3):
                                if len(extracted_bits) >= num_bits:
                                    return extracted_bits
                                extracted_bits.append(get_bit(int(frame[y, x, c])))
        else:
            # Sequential extraction: flatten the channel array and read bits
            # in raster order, capped at num_bits.
            if channel_mode == 'luma':
                flat = plane.flatten()
            else:
                flat = frame.flatten()
            limit = min(num_bits, len(flat))
            for i in range(limit):
                extracted_bits.append(get_bit(int(flat[i])))

        return extracted_bits

    @classmethod
    def embed_message(cls, frames: List[Tuple[int, np.ndarray]],
                     encrypted_data: bytes,
                     progress_callback: Optional[Callable] = None,
                     regions_by_frame: Optional[dict] = None,
                     bit_position: int = 0,
                     channel_mode: str = 'rgb') -> dict:
        """Embed an encrypted message across multiple video frames.

        Distributes the payload across as many frames as needed.
        The payload layout inside the combined bit stream is:
          [ 4-byte length header ][ RS-encoded encrypted data ]

        The length header lets the extractor know when to stop reading
        without needing any out-of-band metadata.

        Capacity check: raises ValueError if the total bit capacity
        of the selected frames is insufficient for the payload.

        Args:
            frames: List of (frame_index, frame_data) tuples to embed into
            encrypted_data: AES-encrypted message bytes
            progress_callback: Optional fn(progress%, step_str) for UI updates
            regions_by_frame: Optional dict mapping frame_index -> region list
            bit_position: LSB position to use (0 = standard LSB)
            channel_mode: 'rgb' or 'luma'

        Returns:
            Dict with modified_frames, bits_embedded, data_length,
            protected_length, and frames_used
        """
        # Apply Reed-Solomon error correction before embedding.
        protected_data = cls.apply_error_correction(encrypted_data)

        # Prepend a 4-byte big-endian length so the extractor knows exactly
        # how many bytes of RS-encoded data to read back.
        data_length = len(protected_data)
        length_bytes = data_length.to_bytes(4, byteorder='big')
        full_data = length_bytes + protected_data

        # Convert the complete payload to a flat bit list for embedding.
        all_bits = list(cls.data_to_bits(full_data))

        def frame_capacity_bits(frame: np.ndarray, regions: Optional[list]) -> int:
            """Calculate how many bits can be embedded in a frame (or regions)."""
            height, width = frame.shape[:2]
            channels = 1 if channel_mode == 'luma' else 3
            if not regions:
                return height * width * channels

            cap = 0
            for r in regions:
                try:
                    x0 = int(r.get('x', 0))
                    y0 = int(r.get('y', 0))
                    rw = int(r.get('width', 0))
                    rh = int(r.get('height', 0))
                except Exception:
                    continue

                x0 = max(0, min(width, x0))
                y0 = max(0, min(height, y0))
                x1 = max(0, min(width, x0 + max(0, rw)))
                y1 = max(0, min(height, y0 + max(0, rh)))
                if x1 <= x0 or y1 <= y0:
                    continue
                cap += (x1 - x0) * (y1 - y0) * channels
            return cap

        # Compute total capacity across all selected frames and validate.
        total_capacity = 0
        for frame_idx, frame in frames:
            regions = None
            if regions_by_frame is not None:
                regions = regions_by_frame.get(frame_idx)
            total_capacity += frame_capacity_bits(frame, regions)

        if len(all_bits) > total_capacity:
            raise ValueError(
                f"Data too large: {len(all_bits)} bits needed, {total_capacity} bits available"
            )

        # Embed the bit stream frame-by-frame, stopping once all bits
        # have been placed.  Frames beyond what is needed are left unmodified.
        modified_frames = {}
        current_bit = 0

        for i, (frame_idx, frame) in enumerate(frames):
            if current_bit >= len(all_bits):
                break

            regions = None
            if regions_by_frame is not None:
                regions = regions_by_frame.get(frame_idx)
            frame_capacity = frame_capacity_bits(frame, regions)
            # Slice only the bits that fit in this frame.
            bits_for_frame = all_bits[current_bit:current_bit + frame_capacity]

            modified_frame, bits_used = cls.embed_in_frame(
                frame,
                bits_for_frame,
                bit_position=bit_position,
                regions=regions,
                channel_mode=channel_mode
            )
            modified_frames[frame_idx] = modified_frame
            current_bit += bits_used

            if progress_callback:
                progress = ((i + 1) / len(frames)) * 100
                progress_callback(progress, f"Embedding in frame {frame_idx}")

        return {
            'modified_frames': modified_frames,
            'bits_embedded': current_bit,
            'data_length': len(encrypted_data),
            'protected_length': data_length,
            'frames_used': len(modified_frames)
        }

    @classmethod
    def extract_message(cls, frames: List[Tuple[int, np.ndarray]],
                       progress_callback: Optional[Callable] = None,
                       regions_by_frame: Optional[dict] = None,
                       bit_position: int = 0,
                       channel_mode: str = 'rgb') -> bytes:
        """Extract an encrypted message from multiple video frames.

        Reads LSBs from the frames in order, parses the 4-byte length header
        to determine how many bytes to collect, then decodes the Reed-Solomon
        error-correcting codes to recover the original encrypted bytes.

        Args:
            frames: List of (frame_index, frame_data) tuples to read from
            progress_callback: Optional fn(progress%, step_str) for UI updates
            regions_by_frame: Optional dict mapping frame_index -> region list
            bit_position: LSB position that was used during embedding
            channel_mode: 'rgb' or 'luma' (must match embedding)

        Returns:
            Extracted encrypted data bytes (before AES decryption)
        """
        all_extracted_bits = []

        # State tracking: once the length header is parsed we know when to stop.
        header_extracted = False
        data_length = 0

        for i, (frame_idx, frame) in enumerate(frames):
            regions = None
            if regions_by_frame is not None:
                regions = regions_by_frame.get(frame_idx)

            # Determine how many bits can exist in this frame.
            if channel_mode == 'luma':
                plane_size = frame[:, :, 1].size
                num_bits = plane_size
            else:
                num_bits = frame.size

            frame_bits = cls.extract_from_frame(
                frame,
                num_bits,
                bit_position=bit_position,
                regions=regions,
                channel_mode=channel_mode
            )
            all_extracted_bits.extend(frame_bits)

            # Parse the length header as soon as we have enough bits.
            # This tells us how many total bytes of RS-encoded data to expect.
            if not header_extracted and len(all_extracted_bits) >= cls.LENGTH_HEADER_BITS:
                header_bits = all_extracted_bits[:cls.LENGTH_HEADER_BITS]
                header_bytes = cls.bits_to_bytes(header_bits)
                data_length = int.from_bytes(header_bytes, byteorder='big')
                header_extracted = True

                # Sanity-check the decoded length to detect obviously wrong
                # values that would cause the extractor to read garbage data.
                if data_length <= 0 or data_length > 100 * 1024 * 1024:  # Max 100 MB
                    raise ValueError(f"Invalid data length detected: {data_length}")

            # Stop reading frames once we have all the bits we need.
            total_bits_needed = cls.LENGTH_HEADER_BITS + (data_length * 8)
            if header_extracted and len(all_extracted_bits) >= total_bits_needed:
                break

            if progress_callback:
                progress = ((i + 1) / len(frames)) * 100
                progress_callback(progress, f"Extracting from frame {frame_idx}")

        if not header_extracted:
            raise ValueError("Could not extract data length header")

        # Slice out just the payload bits (skip the 4-byte header).
        data_bits = all_extracted_bits[cls.LENGTH_HEADER_BITS:cls.LENGTH_HEADER_BITS + (data_length * 8)]

        # Convert bits back to bytes.
        protected_data = cls.bits_to_bytes(data_bits)

        # Decode Reed-Solomon error correction to recover the original
        # encrypted bytes, correcting any bit-level errors along the way.
        try:
            original_data = cls.decode_error_correction(protected_data, ecc_symbols=ecc_symbols)
            return original_data
        except Exception as e:
            raise ValueError(f"Failed to decode data: {e}")

    @classmethod
    def calculate_embedding_capacity(cls, frame: np.ndarray) -> int:
        """Calculate embedding capacity for a single frame.

        Each pixel channel can store 1 bit (the LSB).  The total frame
        capacity is frame.size bits (H * W * channels).  We reserve
        ~10% for Reed-Solomon overhead, giving the usable capacity.

        Args:
            frame: Video frame (H x W x 3 uint8 numpy array)

        Returns:
            Usable capacity in bytes after accounting for ECC overhead
        """
        # Total bits = height * width * channels (1 bit per channel per pixel).
        total_bits = frame.size
        # Reserve 10% for Reed-Solomon ECC check symbols.
        usable_bits = int(total_bits * 0.9)
        return usable_bits // 8
