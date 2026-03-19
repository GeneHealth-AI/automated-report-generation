import boto3
import os
import ObtainProteinMutations
from PersonalizedDrugPrediction import generate_drug_prediction_report

from GenerateVariantReport import generate_variant_report
from NewReportTool import intake_vcf
from Getproteins import extract_and_write_mutations
from Getproteins import extract_mutations
import GenerateVCFs
from pipeline.ProteinCalculation import ProteinScoreCalculation
from GenerateVCFs import RunUpdate
from GenerateVCFs import RunUpdateLocal
import logging
import watchtower
sqs = boto3.client('sqs')
s3 = boto3.client('s3')
logger = logging.getLogger("backup")
logger.setLevel(logging.INFO)
cw_handler = watchtower.CloudWatchLogHandler(log_group="backup-script-logs")
logger.addHandler(cw_handler)

logger = logging.getLogger(__name__)
queue_url = 'https://sqs.us-east-2.amazonaws.com/339712911975/ReportQueue'
#Recieves message when VCF is upload to s3 Bucket 

#extract_and_write_mutations(f"{filename}_output.txt",f"{filename}_proteins.txt")
def poll_sqs_queue():
    while True:
        #receive message from SQS queue
        response = sqs.receive_message(
        QueueUrl=queue_url,
        MaxNumberOfMessages=1
    )

        if 'Messages' in response:
            message = response['Messages'][0]
            receipt_handle = message['ReceiptHandle']
            file_name = message['Body']
            sqs.delete_message(
                QueueUrl=queue_url,
                ReceiptHandle=receipt_handle
            )
            #process the file
            vcf_paths, all_rsid_allele = RunUpdate(s3_prefix = "SUS20250205081-A_001_100x_2/01.RawData/do1qG_b72a21/")
            for i in range(len(vcf_paths)):
                path = vcf_paths[i]
                mutations = extract_mutations(path)
                rsidallele = [mutation.split('\t')[0] for mutation in mutations]
                mutwscore = ProteinScoreCalculation(mutations) # file_name should be a fastq file 
                print("About to generate drug report")
                #try:
                #    generate_drug_metabolism_report(rsidallele,file_name)
                ##except Exception:
                #    print("metab issue")
                print("Drug report -=rated")
                intake_vcf(mutwscore,'Fayes')
                print('Disease report generated')
                generate_variant_report(file_name)
                print('Variant report generated')
                generate_drug_prediction_report(mutwscore,file_name)
                print('Personalized drug prediction report generated')
                
                response = sqs.send_message(
                    QueueUrl='https://sqs.us-east-2.amazonaws.com/339712911975/EC2toSecondLambdaQueue',
                    MessageBody=file_name
                    )

def RunReportAndAnnotation(buckets):
    # As the formats for getting the exomes is inconsistent this takes in directories that contain the paired 2c
    vcf_paths, all_rsid_allele = RunUpdateLocal(buckets)
    for i in range(len(vcf_paths)):
        path = vcf_paths[i]
        name = path.split('_')[-3]
        logger.info(f"Generated report for {name}")
        mutations = extract_mutations(path)
        rsidallele = [mutation.split('\t')[0] for mutation in mutations]
        mutwscore = ProteinScoreCalculation(mutations) # file_name should be a fastq file 
        print("About to generate drug report")
        mwsreport = '\n'.join(mutwscore)
        s3.put_object(Bucket='ghcompletedreports', Key=name + "/personalized_drug_report", Body=mwsreport.encode('utf-8'))
        logger.info(f"Uploaded mutations and scores for {name}")
        try:
            generate_drug_metabolism_report(rsidallele,file_name)
            logger.info(f"Metabolism Report Generated for {name}")
        except Exception:
            logger.info(f"Metabolism Report Generation error for {name}")
        intake_vcf(mutwscore,path)
        logger.info(f"Drug report generated for {name}")
        generate_variant_report(path)
        logger.info(f'Variant report generated for {name}')
        generate_drug_prediction_report(mutwscore,name)
        logger.info(f'Personalized drug prediction report generate for {name}')
def RunReportAlreadyAnnotated(path,name):
    # This will run the report with the annotated vcf locally provided in path
     # Obtain name, current format naming corresponds to this
    logger.info(f"Generating report for {name}")
    
    # Get mutations and calculation scores
    mutations = extract_mutations(path)
    rsidallele = [mutation.split('\t')[0] for mutation in mutations]
    mutwscore = ProteinScoreCalculation(mutations) # file_name should be a fastq file 
    print("About to generate drug report")
    mwsreport = ''.join(mutwscore)
    
    # uploaded rsIDs, proteins, and scores to name's directory in ghcompletedreports s3 bucket 
    s3.put_object(Bucket='ghcompletedreports', Key=name + "/personalized_drug_report", Body=mwsreport.encode('utf-8'))
    logger.info(f"Uploaded mutations and scores for {name}")
    
    # Generates drug metabolism report and logs error if occurs
    try:
        generate_drug_metabolism_report(rsidallele,file_name)
        logger.info(f"Metabolism Report Generated for {name}")
    except Exception:
        logger.info(f"Metabolism Report Generation error for {name}")
    intake_vcf(mutwscore,name)
    logger.info(f"Drug report generated for {name}")
    #generate_variant_report(path)
    #logger.info(f'Variant report generated for {name}')
    generate_drug_prediction_report(mutwscore,name)
    logger.info(f'Personalized drug prediction report generate for {name}')


def main():
    poll_sqs_queue()
entry = [['/home/ec2-user/completevcf/mrh1h_4315f3_CKDN250005383-1A_22T5TFLT4_L4_output.txt','mrh1h_4315f3']]
for r in entry:
    RunReportAlreadyAnnotated(r[0],r[1])