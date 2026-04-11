# SPECIFICATIONS

Data commonly starts as a stack of files on a drive. Turning this into a high quality products that drive decision making, innovations, and transparency is challenging.

The purpose of this package is to manage such file storage areas (workspaces) focusing on the management and publication of data commodities aligned on the FAIR data principles and easy to consume by both humans and machines. 

The objectives are to:
- create an workspace interactive shell to navigate and manage workspace the workspace
    - the shell should be implented using prompt_toolkit and Typer
- create and maintain pydantic classes representing the various entities
- equip the classes with various management methods for maintaining and index the content

## Workspaces

A workspace is a directory tree holding files surrounding a particular dataset or data collection.

A workspace is a space for a data manager to put together data products for publication/dissemination or archival purposes.

Tasks include:
- exploring and understanding the data
- assessing and improving the quality of the data
- compiling and inferring metadata
- preparing documentation for various audience
- ensuring Ai readiness
- creating data products from the raw or master data
- loading data and metadata into databases and knowledge graphs for integration in APIs
- ensuring compliance with best practices
- for sensitive data, assess and reduce the risk of disclosure and enforce privacy policies

To perform this tasks, a data manager use other packages, utilities, amd AI agents. Some of these tools may leverage this package.

A workspace is associated with a root directory.

A workspace can provide various statistics on its content (file counts, size/usage, etc.)

### Workspace folder structure

While this is not a hard requirement, the following folder naming convention and organization is recommended:
- code: processing script/programs
- docs: human readable data documentation
- data: microdata, macrodata, secondary data
- meta: machine actionable metadata
- work,temp: temporary or intermediate files 
- .dartfx: a private subdirectory used to store workspace configuration, state, and other operational files

### .dartfx

The .dartfx directory holds configuration and state files for the workspace.

- brain: RDF knowledge base for the workspace (turtle files, platform specific graphs, internal metadata)
- skills: AI skills used in the workspace
- agents: AI agents used in the workspace
- prompts: AI prompts used in the workspace
- hooks: AI skills used in the workspace
- mcp: MCP servers used in the workspace

The default directory name is .dartfx but can be set using a DARTFX_WORKSPACE_DIR environment variable or a workspace .env configuration file. 

## Files

### File types
Files in a workspace can be classified as:
- data
- metadata
- documentation
- code
- other

Files can also be compressed in formats such as zip, gzip, bz2, xz, etc.
- A compressed file can hold a single file or a tree of files and directories
- If a compressed file holds a single file, it can be treated as a regular file
- If a compressed file holds a tree of files and directories, it can be treated as a directory

### Data Files

The collection of data in a workspace can range for a single data file or a hierarchical datasets, to time series, longitudinal studies, or other complex data structures. 

Data files can hold observation level microdata, aggregates data tables or indicators, or store secondary reference data.

Data files formats can be:
- text: CSV / delimited, fixed
- open: JSON, parquet (binary but open format)
- proprietary: SAS, Stata, SPSS, Excel

### Metadata Files (machine actionable)

Metadata in this context refers to machine actionable documentation and knowledge about the data, commonly based on standards.

These are typically stored in JSON/YAML, RDF (turtle, json-ld, N3), XML formats

### Documentation Files (human readable)

Documentation file hold unstructured human readable information about the data. 

Documentation files formats include:
- MS-Office: word, powerpoint
- PDF
- Markdown
- HTML
- Text

Documentation files may be categorized as:
- report
- technical
- methodological
- user guide
- administrative
- data dictionary
- analytical

### Code Files

 Code files are scripts, programs, syntax files used to produce (collect, cleanse, QA, transform) or analyze the data

These are text file holding code  written in a specific syntax, including:
- programming languages: Python, Java, Rust, C/C++, JavaScript, etc.
- statistical packages: R, SAS, Stata, SPSS, etc.
- Command shell scripts: .sh, .bat, .cmd, etc.

### Compressed Files

Compressed files hold one of more files in a flat or tree like directory structure.

It is important to differentiate between mixed bags of files and a compressed single file (e.g a data file).

The formats depends on the compression algorithm:

- **[ZIP (.zip)](https://www.resourcespace.com/glossary/compression):** The most universal format, natively supported by Windows and macOS. It primarily uses the **DEFLATE** algorithm, which combines [LZ77 and Huffman coding](https://www.tessa-dam.com/en/wiki-en-reader/zip-file/).
- **7z (.7z):** An open-source format known for high compression ratios. Its default algorithm is **LZMA** (Lempel-Ziv-Markov chain Algorithm) or **LZMA2**, which offers better multi-threading support.
- **[RAR (.rar)](https://apyhub.com/blog/all-about-file-compression-rar-zip-7z-explained):** A proprietary format often used for large files. It uses the **LZSS** algorithm combined with Huffman coding and supports advanced features like error recovery.
- **[Gzip (.gz)](https://konnectwithdata.com.au/choosing-the-right-compression-algorithm-for-data-engineering-workloads/):** The standard for Unix-like systems and web traffic. Like ZIP, it uses the [DEFLATE algorithm](https://www.happykhan.com/posts/linux-compression-intro).
- **[Bzip2 (.bz2)](https://xceed.com/documentation/xceed-streaming-compression-for-activex/index.html):** Offers higher compression than Gzip but is slower. It is based on the **Burrows-Wheeler Transform** (BWT).
- **[XZ (.xz)](https://ukiahsmith.com/blog/which-compression-format-to-use-for-archiving/):** A modern format that uses [LZMA2 compression](https://www.2brightsparks.com/resources/articles/data-compression.html), often replacing Bzip2 in Linux distributions due to its superior efficiency.
- **Brotli (.br):** Developed by Google primarily for web content (HTML, CSS, JS). It often outperforms Gzip for text-based data.
- **Zstandard (.zst / Zstd):** Created by Meta (Facebook), designed for a balance of high speed and high compression. 

## Knowledge Base

A key feature of a workspace is the available of an RDF knowledge base to capture information about the files and metadata in generic highly granular 

Tools are expected to produce knowledge in RDF, typically as turtle files, that can be loaded on triple stores

This knowledge base lives in a dedicated directory (e.g. `kb`), with dedicated sub-folders for file and triple-store storage, such as:
- `turtle`
- `oxigraph`
- `qlever`
- `virtuoso`

## Spaces

A "space" is a virtual storage area that groups workspaces and can be used to:
- control access to the underlying workspace
- limit the total amount of storage used by its underlying workspace
- report on content

## Phase 1: Core Workspace Management
In this phase we focus on the workspace management aspect of the package.
We should be able to start the:
- start the shell 
- initialize a workspace
- navigate the structure using `cd` and `ls` like commands (/ being the workspace root)
- create, move, rename, delete files and directories
- scan the workspace an maintain an inventory of its content
    - each file should be register as a resource in the RDF knowledge base
- categorize file resources (auto detect and manually edit)
- generate statistics in the content (file counts, size/usage, etc.)
    
### File resource
- a file resource can be describe unsing dublin core os similar standard (potentially with extensions)
- it should hold metadata such as size, create/update date, hash, etc.
- each file can have a corresponding RDF description (turtle file) in the knowledge base
- suggest a good mechanims to name the resource files
    




