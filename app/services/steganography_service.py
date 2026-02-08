"""
Steganography Service - LSB embedding and extraction with Reed-Solomon error correction
"""

import numpy as np
from typing import List, Tuple, Optional, Generator, Callable
import reedsolo


class SteganographyService:
    """Service for LSB steganography operations."""
    
    # Reed-Solomon error correction symbols
    RS_ECC_SYMBOLS = 10
    
    # Data length header size (4 bytes = 32 bits for length up to ~4GB)
    LENGTH_HEADER_BITS = 32
    
    @classmethod
    def data_to_bits(cls, data: bytes) -> Generator[int, None, None]:
        """
        Convert bytes to bit generator.
        
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
        """
        Convert list of bits to bytes.
        
        Args:
            bits: List of bits (0 or 1)
            
        Returns:
            Bytes object
        """
        # Pad to byte boundary
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
        """
        Apply Reed-Solomon error correction to data.
        
        Args:
            data: Original data bytes
            
        Returns:
            Data with error correction codes appended
        """
        rs = reedsolo.RSCodec(cls.RS_ECC_SYMBOLS)
        return bytes(rs.encode(data))
    
    @classmethod
    def decode_error_correction(cls, data: bytes) -> bytes:
        """
        Decode and correct errors using Reed-Solomon.
        
        Args:
            data: Data with error correction codes
            
        Returns:
            Corrected original data
        """
        rs = reedsolo.RSCodec(cls.RS_ECC_SYMBOLS)
        try:
            decoded = rs.decode(data)
            # rs.decode returns tuple (decoded_msg, decoded_msgecc, errata_pos)
            return bytes(decoded[0]) if isinstance(decoded, tuple) else bytes(decoded)
        except reedsolo.ReedSolomonError as e:
            raise ValueError(f"Error correction failed: {e}")
    
    @classmethod
    def embed_in_frame(cls, frame: np.ndarray, 
                       data_bits: List[int],
                       bit_position: int = 0,
                       regions: Optional[List[dict]] = None,
                       channel_mode: str = 'rgb') -> Tuple[np.ndarray, int]:
        """
        Embed data bits into frame using LSB technique.
        
        Args:
            frame: Video frame (numpy array)
            data_bits: List of bits to embed
            bit_position: LSB position to modify (0 = least significant)
            
        Returns:
            Tuple of (modified frame, bits embedded count)
        """
        if channel_mode not in ('rgb', 'luma'):
            raise ValueError("channel_mode must be 'rgb' or 'luma'")

        work_frame = frame.copy()

        # If luma-only embedding, convert to YCrCb and operate on Y channel.
        if channel_mode == 'luma':
            import cv2
            ycrcb = cv2.cvtColor(work_frame, cv2.COLOR_BGR2YCrCb)
            plane = ycrcb[:, :, 0]
        else:
            ycrcb = None
            plane = None

        bits_embedded = 0
        bit_iter = iter(data_bits)

        def set_bit(value: int, bit: int) -> int:
            mask = ~(1 << bit_position)
            return (value & mask) | (bit << bit_position)

        if regions:
            # Content-aware embedding: embed bits only inside the provided regions.
            for region in regions:
                x0 = int(region.get('x', 0))
                y0 = int(region.get('y', 0))
                w = int(region.get('width', 0))
                h = int(region.get('height', 0))

                if w <= 0 or h <= 0:
                    continue

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
                                if ycrcb is not None:
                                    ycrcb[:, :, 0] = plane
                                    work_frame = cv2.cvtColor(ycrcb, cv2.COLOR_YCrCb2BGR)
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
            # Default sequential embedding over all channels.
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

        if channel_mode == 'luma':
            import cv2
            ycrcb[:, :, 0] = plane
            work_frame = cv2.cvtColor(ycrcb, cv2.COLOR_YCrCb2BGR)

        return work_frame.astype(np.uint8), bits_embedded
    
    @classmethod
    def extract_from_frame(cls, frame: np.ndarray,
                          num_bits: int,
                          bit_position: int = 0,
                          regions: Optional[List[dict]] = None,
                          channel_mode: str = 'rgb') -> List[int]:
        """
        Extract data bits from frame using LSB technique.
        
        Args:
            frame: Video frame (numpy array)
            num_bits: Number of bits to extract
            bit_position: LSB position to read from
            
        Returns:
            List of extracted bits
        """
        if channel_mode not in ('rgb', 'luma'):
            raise ValueError("channel_mode must be 'rgb' or 'luma'")

        extracted_bits: List[int] = []

        if channel_mode == 'luma':
            import cv2
            ycrcb = cv2.cvtColor(frame, cv2.COLOR_BGR2YCrCb)
            plane = ycrcb[:, :, 0]
        else:
            plane = None

        def get_bit(value: int) -> int:
            return (value >> bit_position) & 1

        if regions:
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
        """
        Embed encrypted message across multiple frames.
        
        Args:
            frames: List of (frame_index, frame_data) tuples
            encrypted_data: Encrypted message bytes
            progress_callback: Optional callback for progress updates
            
        Returns:
            Dictionary with modified frames and metadata
        """
        # Apply error correction
        protected_data = cls.apply_error_correction(encrypted_data)
        
        # Add length header (4 bytes big-endian)
        data_length = len(protected_data)
        length_bytes = data_length.to_bytes(4, byteorder='big')
        full_data = length_bytes + protected_data
        
        # Convert to bits
        all_bits = list(cls.data_to_bits(full_data))
        
        def frame_capacity_bits(frame: np.ndarray, regions: Optional[list]) -> int:
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
        
        # Embed across frames
        modified_frames = {}
        current_bit = 0
        
        for i, (frame_idx, frame) in enumerate(frames):
            if current_bit >= len(all_bits):
                break
            
            # Calculate bits to embed in this frame
            regions = None
            if regions_by_frame is not None:
                regions = regions_by_frame.get(frame_idx)
            frame_capacity = frame_capacity_bits(frame, regions)
            bits_for_frame = all_bits[current_bit:current_bit + frame_capacity]
            
            # Embed bits
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
        """
        Extract encrypted message from frames.
        
        Args:
            frames: List of (frame_index, frame_data) tuples
            progress_callback: Optional callback for progress updates
            
        Returns:
            Extracted encrypted data bytes
        """
        all_extracted_bits = []
        
        # First, extract enough bits to get the length header
        header_extracted = False
        data_length = 0
        
        for i, (frame_idx, frame) in enumerate(frames):
            # Extract all bits from this frame
            regions = None
            if regions_by_frame is not None:
                regions = regions_by_frame.get(frame_idx)
            # Extract all bits from this frame (for the selected mode)
            if channel_mode == 'luma':
                import cv2
                ycrcb = cv2.cvtColor(frame, cv2.COLOR_BGR2YCrCb)
                plane_size = ycrcb[:, :, 0].size
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
            
            if not header_extracted and len(all_extracted_bits) >= cls.LENGTH_HEADER_BITS:
                # Parse length header
                header_bits = all_extracted_bits[:cls.LENGTH_HEADER_BITS]
                header_bytes = cls.bits_to_bytes(header_bits)
                data_length = int.from_bytes(header_bytes, byteorder='big')
                header_extracted = True
                
                # Validate length
                if data_length <= 0 or data_length > 100 * 1024 * 1024:  # Max 100MB
                    raise ValueError(f"Invalid data length detected: {data_length}")
            
            # Check if we have enough data
            total_bits_needed = cls.LENGTH_HEADER_BITS + (data_length * 8)
            if header_extracted and len(all_extracted_bits) >= total_bits_needed:
                break
            
            if progress_callback:
                progress = ((i + 1) / len(frames)) * 100
                progress_callback(progress, f"Extracting from frame {frame_idx}")
        
        if not header_extracted:
            raise ValueError("Could not extract data length header")
        
        # Extract data bits (skip header)
        data_bits = all_extracted_bits[cls.LENGTH_HEADER_BITS:cls.LENGTH_HEADER_BITS + (data_length * 8)]
        
        # Convert to bytes
        protected_data = cls.bits_to_bytes(data_bits)
        
        # Decode error correction
        try:
            original_data = cls.decode_error_correction(protected_data)
            return original_data
        except Exception as e:
            raise ValueError(f"Failed to decode data: {e}")
    
    @classmethod
    def calculate_embedding_capacity(cls, frame: np.ndarray) -> int:
        """
        Calculate embedding capacity for a single frame.
        
        Args:
            frame: Video frame
            
        Returns:
            Capacity in bytes
        """
        # Each pixel channel can hold 1 bit (LSB)
        total_bits = frame.size
        # Account for error correction overhead
        usable_bits = int(total_bits * 0.9)
        return usable_bits // 8
