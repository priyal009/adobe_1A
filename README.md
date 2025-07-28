\# DotReader PDF Heading Extractor



DotReader is a simple Python-based tool to extract headings from PDF files using `PyMuPDF`. The project runs in a Docker container and supports batch processing of PDFs from the `input` folder, saving outputs to `output`.



---



\##Project Structure



dotreader\_project/

├── Dockerfile

├── main.py

├── requirements.txt

├── input/ # Folder for input PDF files

└── output/ # Folder for extracted heading text files





---



\##How to Use



\### 1. Place your PDF files

Put all PDF files into the `input/` folder.



\### 2. Build the Docker image



```bash

docker build -t dotreader .



Dependencies

Dependencies are listed in requirements.txt, and include:



PyMuPDF (fitz)





Output Format

For each PDF, a .txt file with extracted headings is saved in the output/ folder.

The format remains consistent with the original project output.







