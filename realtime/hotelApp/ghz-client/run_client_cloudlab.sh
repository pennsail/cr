#!/bin/bash
# Run this file from the kube master node in order to run the ghz experiment

# Get the names of all deployments
deployments=$(kubectl get deployments -o custom-columns=":metadata.name" --no-headers)
echo "Deployments: $deployments"

# Loop through each deployment and wait for it to complete
for deployment in $deployments; do
  kubectl rollout status deployment/$deployment
  # echo "Deployment $deployment is ready."
done

# entrypoint is 
echo "ENTRY_POINT: $ENTRY_POINT"

# Get the Cluster IP of grpc-service-1
SERVICE_A_IP=$(kubectl get service $ENTRY_POINT -o=jsonpath='{.spec.clusterIP}')

# Get the NodePort (if available) of grpc-service-1
SERVICE_A_NODEPORT=$(kubectl get service $ENTRY_POINT -o=jsonpath='{.spec.ports[0].nodePort}')

SERVICE_A_URL="$SERVICE_A_IP:50051"

# Export the SERVICE_A_URL as an environment variable
export SERVICE_A_URL

# Display the URL
echo "SERVICE_A_URL: $SERVICE_A_URL"

# if RL_TIERS env is set, then echo it
if [ -n "$RL_TIERS" ]; then
  echo "RL_TIERS: $RL_TIERS"
fi
# if AQM_ENABLED env is set, then echo it
if [ -n "$AQM_ENABLED" ]; then
  echo "AQM_ENABLED: $AQM_ENABLED"
fi

# Print the `CAPACITY` env var of the current pod
echo "Capacity: $CAPACITY"

# Run the client
~/protobuf/ghz-client/clientcall 

copy_deathstar_output() {
  target_file="deathstar_*.output"

  # Loop over all pods
  kubectl get pods -o=jsonpath='{range .items[*]}{.metadata.name}{" "}{.metadata.namespace}{"\n"}{end}' | while read -r pod; do
    pod_name=$(echo "$pod" | cut -d' ' -f1)
    namespace_name=$(echo "$pod" | cut -d' ' -f2)

    echo "Debug: Checking Namespace=$namespace_name, Pod=$pod_name for Target File=$target_file"

    # List matching files in the pod
    matching_files=$(kubectl exec -n "$namespace_name" "$pod_name" -- sh -c "ls /root/ | grep 'deathstar_'")

    if [ -n "$matching_files" ]; then
      echo "Namespace: $namespace_name, Pod: $pod_name has the target files."
      
      # Loop over matching files and copy them individually
      for file in $matching_files; do
        # local_file="${namespace_name}-${pod_name}-$(date +%s)-$file"
        local_file="$file"

        echo "Copying $file to $local_file"
        kubectl cp "$namespace_name/$pod_name:/root/$file" ~/"$local_file"
      done
    else
      echo "Target files not found in Pod $pod_name in Namespace $namespace_name."
    fi
  done
}

copy_deathstar_output
