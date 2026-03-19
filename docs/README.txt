These files are the all the contents necessary to generate the automatic reports.
the blocks directory contains all the text to be fed into to blocks into Claude.

np_full_info has protein data to enrich the protein info to reduce hallucinations.

block_generator.py fills out the blocks and has a parallelized and non-parallelized versions.

report_blocks.py contains enums and other data for the report block class.

ReportGenerator.py can load report templates, instaniate a class instance, and makes the call to generate a report.

StartReportGenerator.py is the progrma that should be called when the program starts running. It creates the Report class instance, generates the report, and then uploads it to a S3 bucket. 