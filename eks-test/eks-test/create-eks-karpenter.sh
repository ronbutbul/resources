# create EKS cluster
eksctl create cluster -f cluster.yml

------------------------------------------------------------------------------------------------------------------------------------------------------------------

# export relevant variables
export CLUSTER_NAME=eks-karpenter-test2
export KARPENTER_VERSION=v0.32.1
export CLUSTER_ENDPOINT="$(aws eks describe-cluster --name ${CLUSTER_NAME} --query "cluster.endpoint" --output text)"
export AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query 'Account' --output text)

------------------------------------------------------------------------------------------------------------------------------------------------------------------

# create IAM role with relevant policies via cli
echo '{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Principal": {
                "Service": "ec2.amazonaws.com"
            },
            "Action": "sts:AssumeRole"
        }
    ]
}' > node-trust-policy.json

------------------------------------------------------------------------------------------------------------------------------------------------------------------

# iam roles for the instances that will be created
aws iam create-role --role-name "KarpenterInstanceNodeRole" \
    --assume-role-policy-document file://node-trust-policy.json

aws iam attach-role-policy --role-name "KarpenterInstanceNodeRole" \
    --policy-arn arn:aws:iam::aws:policy/AmazonEKSWorkerNodePolicy

aws iam attach-role-policy --role-name "KarpenterInstanceNodeRole" \
    --policy-arn arn:aws:iam::aws:policy/AmazonEKS_CNI_Policy

aws iam attach-role-policy --role-name "KarpenterInstanceNodeRole" \
    --policy-arn arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly

aws iam create-instance-profile --instance-profile-name KarpenterInstanceProfile

aws iam add-role-to-instance-profile --instance-profile-name KarpenterInstanceProfile --role-name KarpenterInstanceNodeRole

# check the result
aws iam get-instance-profile --instance-profile-name KarpenterInstanceProfile

------------------------------------------------------------------------------------------------------------------------------------------------------------------

# create IAM role and policy that the karpenter controller will use to provision new instances

echo '{
    "Statement": [
        {
            "Action": [
                "ssm:GetParameter",
				"iam:GetInstanceProfile",
				"iam:CreateInstanceProfile",
				"iam:TagInstanceProfile",
				"iam:AddRoleToInstanceProfile",                
                "iam:PassRole",
                "ec2:DescribeImages",
                "ec2:TerminateInstances",
                "ec2:RunInstances",
                "ec2:DescribeSubnets",
                "ec2:DescribeSecurityGroups",
                "ec2:DescribeLaunchTemplates",
                "ec2:DescribeInstances",
                "ec2:DescribeInstanceTypes",
                "ec2:DescribeInstanceTypeOfferings",
                "ec2:DescribeAvailabilityZones",
                "ec2:DeleteLaunchTemplate",
                "ec2:CreateTags",
                "ec2:CreateLaunchTemplate",
                "ec2:CreateFleet",
                "ec2:DescribeSpotPriceHistory",
                "pricing:GetProducts"
            ],
            "Effect": "Allow",
            "Resource": "*",
            "Sid": "Karpenter"
        },
        {
            "Action": "ec2:TerminateInstances",
            "Condition": {
                "StringLike": {
                    "ec2:ResourceTag/Name": "*karpenter*"
                }
            },
            "Effect": "Allow",
            "Resource": "*",
            "Sid": "ConditionalEC2Termination"
        }
    ],
    "Version": "2012-10-17"
}' > controller-policy.json


aws iam create-policy --policy-name KarpenterControllerPolicy-${CLUSTER_NAME} --policy-document file://controller-policy.json
eksctl utils associate-iam-oidc-provider --cluster ${CLUSTER_NAME} --approve

------------------------------------------------------------------------------------------------------------------------------------------------------------------

eksctl create iamserviceaccount \
  --cluster "${CLUSTER_NAME}" --name karpenter --namespace karpenter \
  --role-name "KarpenterControllerRole-${CLUSTER_NAME}" \
  --attach-policy-arn "arn:aws:iam::${AWS_ACCOUNT_ID}:policy/KarpenterControllerPolicy-${CLUSTER_NAME}" \
  --role-only \
  --approve

------------------------------------------------------------------------------------------------------------------------------------------------------------------

# add tags to subnets so karpenter knows the subnets to use
for NODEGROUP in $(aws eks list-nodegroups --cluster-name ${CLUSTER_NAME} \
    --query 'nodegroups' --output text); do aws ec2 create-tags \
        --tags "Key=karpenter.sh/discovery,Value=${CLUSTER_NAME}" \
        --resources $(aws eks describe-nodegroup --cluster-name ${CLUSTER_NAME} \
        --nodegroup-name $NODEGROUP --query 'nodegroup.subnets' --output text )
done

------------------------------------------------------------------------------------------------------------------------------------------------------------------

# add tags to security groups
NODEGROUP=$(aws eks list-nodegroups --cluster-name ${CLUSTER_NAME} \
    --query 'nodegroups[0]' --output text)
 
LAUNCH_TEMPLATE=$(aws eks describe-nodegroup --cluster-name ${CLUSTER_NAME} \
    --nodegroup-name ${NODEGROUP} --query 'nodegroup.launchTemplate.{id:id,version:version}' \
    --output text | tr -s "\t" ",")

SECURITY_GROUPS=$(aws eks describe-cluster \
    --name ${CLUSTER_NAME} --query cluster.resourcesVpcConfig.clusterSecurityGroupId | tr -d '"')

aws ec2 create-tags \
    --tags "Key=karpenter.sh/discovery,Value=${CLUSTER_NAME}" \
    --resources ${SECURITY_GROUPS}

------------------------------------------------------------------------------------------------------------------------------------------------------------------

# Update the aws-auth ConfigMap in the cluster to allow the nodes that use the KarpenterInstanceNodeRole IAM role to join the cluster
eksctl create iamidentitymapping \
  --username system:node:{{EC2PrivateDNSName}} \
  --cluster "${CLUSTER_NAME}" \
  --arn "arn:aws:iam::${AWS_ACCOUNT_ID}:role/KarpenterInstanceNodeRole" \
  --group system:bootstrappers \
  --group system:nodes

------------------------------------------------------------------------------------------------------------------------------------------------------------------


#https://github.com/aws/karpenter-provider-aws/tree/main/pkg/apis/crds
#kubectl create -f https://github.com/aws/karpenter-provider-aws/tree/main/pkg/apis/crds/karpenter.k8s.aws_ec2nodeclasses.yaml
#kubectl create -f https://github.com/aws/karpenter-provider-aws/tree/main/pkg/apis/crds/karpenter.sh_nodeclaims.yaml
#kubectl create -f https://github.com/aws/karpenter-provider-aws/tree/main/pkg/apis/crds/karpenter.sh_nodepools.yaml

------------------------------------------------------------------------------------------------------------------------------------------------------------------

  helm install karpenter oci://public.ecr.aws/karpenter/karpenter --version v0.32.1 --namespace karpenter --create-namespace  -f karpenter-values.yaml \
  --set serviceAccount.annotations."eks\.amazonaws\.com/role-arn"="arn:aws:iam::${AWS_ACCOUNT_ID}:role/KarpenterControllerRole-${CLUSTER_NAME}" \
  --set settings.aws.clusterName=${CLUSTER_NAME} \
  --set settings.aws.clusterEndpoint=${CLUSTER_ENDPOINT} \
  --set settings.aws.defaultInstanceProfile=KarpenterInstanceProfile \
  --set settings.aws.interruptionQueueName=${CLUSTER_NAME} \
  --set controller.resources.requests.cpu=1 \
  --set controller.resources.requests.memory=1Gi \
  --set controller.resources.limits.cpu=1 \
  --set controller.resources.limits.memory=1Gi \
  --wait

------------------------------------------------------------------------------------------------------------------------------------------------------------------


aws eks update-nodegroup-config --cluster-name eks-karpenter-test2 \
    --nodegroup-name test-workers-2 \
    --scaling-config "minSize=3,maxSize=3,desiredSize=3"






helm install mongo bitnami/mongodb \
  --set architecture=standalone \
  --set useStatefulSet=true \
  --set persistence.enabled=true \
  --set persistence.storageClass="" \
  --set persistence.size=8Gi \
  --set volumePermissions.enabled=true \
  --set volumePermissions.securityContext.runAsUser=0
