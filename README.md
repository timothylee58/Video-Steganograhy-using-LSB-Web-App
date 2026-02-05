# Final Year Project - Video Steganography Using LSB Technique

Video steganography is a vital medium for covert communication, which enables the hiding of confidential and secret data within video files while preserving their visual quality. The Least Significant Bit (LSB) technique has been widely used in video steganography due to its simplicity and efficiency. However, existing LSB-based systems suffer from limitations such as low embedding capacity and vulnerability to steganalysis attacks. 

One of the primary objectives of the project is to increase the embedding capacity further while maintaining the visual integrity of the video. Additionally, with advanced LSB embedding techniques and encryption mechanisms, the systems maximise the amount of data hidden within the video while safeguarding its security and confidentiality. Rigorous testing and evaluation validate the system’s performance and demonstrate its effectiveness in securely embedding and extracting hidden data within video files. The developed video steganography system utilizing the LSB technique offers an efficient and reliable solution for covert communication. 

Built on the research technique, a production-ready web application for hiding encrypted messages within videos using the LSB (Least Significant Bit) technique was created. 
It supports resolutions up to 1440p with configurable encryption strength and cipher modes.

# VidStega app

✨ Features

- Multiple Resolutions: Support for 480p, 720p, 1080p, and 1440p videos
- Flexible Encryption: Choose from AES-128/192/256 with CBC, CTR, GCM, or CFB modes
- Robust Security: PBKDF2 key derivation with 100,000 iterations
- Scalable Architecture: Async processing with Celery and Redis
- Capacity Calculator: Check how much data can be hidden before encoding
- Real-time Progress: WebSocket updates for long-running operations
- RESTful API: Easy integration with any frontend or mobile app 

📄 License
MIT License - see LICENSE file for details.

⚠️ Legal Disclaimer
This software is provided for educational and legitimate privacy purposes only. Users are responsible for complying with local laws and regulations. The authors assume no liability for misuse.

Appropriate Uses:

- Personal privacy protection
- Secure business communication
- Digital watermarking
- Data backup and recovery

Inappropriate Uses:

- Illegal communication
- Circumventing lawful surveillance
- Copyright infringement
- Distribution of illegal content


🙏 Acknowledgments

- OpenCV for video processing
- Cryptography library for encryption
- FastAPI for the web framework
- The steganography research community


#Built with ❤️ for privacy-conscious users worldwide
