"""Provision the private, preview-only GCP service. Run from the repository root.

Requires an existing billing-enabled project and authenticated gcloud CLI.
No token is accepted on the command line or included in the build context.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--project', required=True)
    parser.add_argument('--region', default='us-west1')
    parser.add_argument('--gcloud', default='gcloud')
    args=parser.parse_args()
    project,region=args.project,args.region
    root=Path(__file__).resolve().parent.parent

    def run(*words, capture=False):
        result=subprocess.run([args.gcloud,*words,'--project='+project,'--quiet'],
                              check=True,cwd=root,text=True,stdout=subprocess.PIPE if capture else None)
        return result.stdout.strip() if capture else None

    def ensure(describe, create):
        result=subprocess.run([args.gcloud,*describe,'--project='+project,'--quiet'],
                              cwd=root,text=True,capture_output=True)
        if result.returncode:
            run(*create)

    run('services','enable','run.googleapis.com','cloudbuild.googleapis.com',
        'artifactregistry.googleapis.com','cloudscheduler.googleapis.com',
        'secretmanager.googleapis.com','storage.googleapis.com')
    for name in ('commute-runtime','commute-scheduler','commute-build'):
        ensure(['iam','service-accounts','describe',f'{name}@{project}.iam.gserviceaccount.com'],
               ['iam','service-accounts','create',name,'--display-name='+name])
    runtime=f'commute-runtime@{project}.iam.gserviceaccount.com'
    scheduler=f'commute-scheduler@{project}.iam.gserviceaccount.com'
    builder=f'commute-build@{project}.iam.gserviceaccount.com'
    for suffix,identity in (('cache',runtime),('build',builder)):
        bucket=f'gs://{project}-{suffix}'
        ensure(['storage','buckets','describe',bucket],
               ['storage','buckets','create',bucket,'--location='+region,
                '--uniform-bucket-level-access','--public-access-prevention'])
        run('storage','buckets','add-iam-policy-binding',bucket,
            '--member=serviceAccount:'+identity,'--role=roles/storage.objectAdmin')
        if suffix == 'build':
            run('storage','buckets','add-iam-policy-binding',bucket,
                '--member=serviceAccount:'+identity,'--role=roles/storage.legacyBucketReader')
    ensure(['artifacts','repositories','describe','commute','--location='+region],
           ['artifacts','repositories','create','commute','--location='+region,'--repository-format=docker'])
    run('artifacts','repositories','add-iam-policy-binding','commute','--location='+region,
        '--member=serviceAccount:'+builder,'--role=roles/artifactregistry.writer')
    ensure(['secrets','describe','commute-config'],
           ['secrets','create','commute-config','--replication-policy=automatic'])
    version=run('secrets','versions','add','commute-config','--data-file='+str(root/'config.local.json'),
                '--format=value(name)',capture=True).split('/')[-1]
    run('secrets','add-iam-policy-binding','commute-config',
        '--member=serviceAccount:'+runtime,'--role=roles/secretmanager.secretAccessor')
    image=f'{region}-docker.pkg.dev/{project}/commute/app:latest'
    run('builds','submit','.', '--tag='+image, '--timeout=600s',
        '--service-account=projects/'+project+'/serviceAccounts/'+builder,
        '--gcs-source-staging-dir=gs://'+project+'-build/source',
        '--gcs-log-dir=gs://'+project+'-build/logs')
    run('run','deploy','commute-bar','--image='+image,'--region='+region,
        '--service-account='+runtime,'--no-allow-unauthenticated','--min=0','--max=1',
        '--min-instances=0','--max-instances=1','--cpu-throttling',
        '--concurrency=1','--cpu=1','--memory=512Mi','--timeout=240',
        '--set-env-vars=CACHE_BUCKET='+project+'-cache,COMMUTE_CONFIG_FILE=/secrets/config/config.json,DRY_RUN=true',
        '--set-secrets=/secrets/config/config.json=commute-config:'+version)
    run('run','services','add-iam-policy-binding','commute-bar','--region='+region,
        '--member=serviceAccount:'+scheduler,'--role=roles/run.invoker')
    url=run('run','services','describe','commute-bar','--region='+region,'--format=value(status.url)',capture=True)
    schedule=['--location='+region,'--schedule=* 14-16 * * 1-5',
              '--time-zone=America/Los_Angeles','--uri='+url+'/tick','--http-method=POST',
              '--oidc-service-account-email='+scheduler,'--oidc-token-audience='+url,
              '--attempt-deadline=240s','--max-retry-attempts=0']
    ensure(['scheduler','jobs','describe','commute-tick','--location='+region],
           ['scheduler','jobs','create','http','commute-tick',*schedule])
    run('scheduler','jobs','update','http','commute-tick',*schedule)
    lunch_schedule = [word if not word.startswith('--schedule=') else '--schedule=30-39 11 * * 1-5'
                      for word in schedule]
    ensure(['scheduler','jobs','describe','lunch-tick','--location='+region],
           ['scheduler','jobs','create','http','lunch-tick',*lunch_schedule])
    run('scheduler','jobs','update','http','lunch-tick',*lunch_schedule)
    state=dict(project=project,region=region,url=url,mode='preview_only',config_version=version)
    (root/'data').mkdir(exist_ok=True)
    (root/'data'/'deployment.json').write_text(json.dumps(state,indent=2)+'\n')
    print('Preview-only deployment ready. BUSY cloud token is still required for device updates.')


if __name__=='__main__':
    main()
