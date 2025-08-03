#!/bin/bash

set_environment_vars() {
    export CAPACITY=$1
    [ -z ${METHOD+x} ] && export METHOD=search-hotel
    
    export CONSTANT_LOAD=false
    export SUBCALL=$2
    export ENTRY_POINT=nginx-web-server
    [ "$METHOD" = "reserve-hotel" -o "$METHOD" = "search-hotel" -o "$METHOD" = "both-hotel" ] && export HOTELAPP=true
    [ "$HOTELAPP" = true ] && export ENTRY_POINT=frontend
    [ "$METHOD" = "compose" -o "$METHOD" = "home-timeline" -o "$METHOD" = "user-timeline" -o "$METHOD" = "all-social" ] && export SOCIALAPP=true 
    [ "$SOCIALAPP" = true ] && export ENTRY_POINT=nginx
    
    export RUN_DURATION=70s
    export LOAD_STEP_DURATION=40s
    set_default_vars
    echo_environment_vars
}

set_default_vars() {
    [ -z ${DEBUG_INFO+x} ] && export DEBUG_INFO=false
    [ -z ${PROFILING+x} ] && export PROFILING=false
    [ -z ${AUTOSCALING+x} ] && export AUTOSCALING=false
    export DOCKER_BUILD=false
}

echo_environment_vars() {
    for var in CAPACITY METHOD CONSTANT_LOAD SUBCALL PROFILING ENTRY_POINT DEBUG_INFO RUN_DURATION WARMUP_LOAD AUTOSCALING; do
        echo "$var: ${!var}"
    done
    source ./envs.sh
}

run_python_script() {
    local script_path=$1
    python "$script_path"
    if [ $? -eq 0 ]; then
        echo "${script_path##*/} ran successfully"
    else
        echo "Python script ${script_path##*/} failed"
        exit 1
    fi
}

scp_file_transfer() {
    local src=$1
    local dest=$2

    if [[ "$src" == *"${node_username}@${node_address}"* ]]; then
        local dest_dir=$(dirname "$dest")
        mkdir -p "$dest_dir"
        scp -P 22 -i "${private_key}" "$src" "$dest"
    else
        local remote_dest="${node_username}@${node_address}:$dest"
        scp -P 22 -i "${private_key}" "$src" "$remote_dest"
    fi
    
    if [ $? -ne 0 ]; then
        echo "SCP command failed. Exiting."
        exit 1
    fi
}

execute_remote_command() {
    local cmd=$1
    ssh -p 22 -i "${private_key}" "${node_username}@${node_address}" "$cmd"
}

handle_file_naming_and_copying() {
    timestamp=$(date "+%m%d_%H%M")
    local filename="social-${METHOD}-plain-${SUBCALL}-capacity-${CAPACITY}.json"
    local localfilename="powercap-${POWER_CAP}-${METHOD}-capacity-${CAPACITY}-${timestamp}.json"
    
    scp_file_transfer "${node_username}@${node_address}:/users/user/protobuf/ghz-client/ghz.output" "$OUTPUT_DIR/${localfilename}.output"
    scp_file_transfer "${node_username}@${node_address}:/users/user/protobuf/ghz-results/${filename}" "$OUTPUT_DIR/${localfilename}"
    scp_file_transfer "${node_username}@${node_address}:/users/user/*.output" "$OUTPUT_DIR/"
}

capture_exported_vars() {
    env | grep '^CAPACITY\|^METHOD\|^CONSTANT_LOAD\|^SUBCALL\|^PROFILING\|^ENTRY_POINT\|^DEBUG_INFO\|^LOAD_INCREASE\|^RUN_DURATION\|^CONCURRENCY\|^WARMUP_LOAD\|^LOAD_STEP_DURATION\|^POWER_CAP\|^TEST_LOAD\|^OVERLOAD_CONTROL' | sed 's/^/export /'
}

perform_remote_operations() {
    scp_file_transfer "./grpc-app/msgraph.yaml" "~/microservice-generator/grpc-app/msgraph.yaml"
    scp_file_transfer "./grpc-app/msgraph.yaml" "~/protobuf/ghz-client/msgraph.yaml"
    scp_file_transfer "./cloudlab/deploy/hardcode.yaml" "~/microservice-generator/cloudlab/deploy/hardcode.yaml"
    
    if [ "$4" = true ]; then
        echo "Skipping k8s redeployment"
    else
        configMapName="msgraph-config"
        execute_remote_command "kubectl delete --all configmap"
        execute_remote_command "kubectl create configmap ${configMapName} --from-file=/users/user/microservice-generator/grpc-app/msgraph.yaml"
        sleep 5

        [ "$HOTELAPP" = true ] && execute_remote_command "export DEBUG_INFO=$DEBUG_INFO && cd /users/user/hotelApp && ./setup-k8s-redeploy.sh hotel > /dev/null"
        
        if [ "$SOCIALAPP" = true ]; then
            execute_remote_command "cd /users/user/hotelApp && export DEBUG_INFO=$DEBUG_INFO && export METHOD=$METHOD && ./setup-k8s-redeploy.sh > /dev/null"
        fi

        [ "$HOTELAPP" != true ] && [ "$SOCIALAPP" != true ] && execute_remote_command "kubectl delete deployment --all > /dev/null && kubectl delete service --all > /dev/null && kubectl apply -f /users/user/microservice-generator/cloudlab/deploy/hardcode.yaml > /dev/null"

        scp_file_transfer "$PROTO_DIR/ghz-client/run_client_cloudlab.sh" "~/protobuf/ghz-client/run_client_cloudlab.sh"
        scp_file_transfer "$PROTO_DIR/ghz-client/clientcall" "~/protobuf/ghz-client/clientcall"

        echo "Waiting for deployment, sleeping for 40 seconds..."
        sleep 40
    fi
    
    execute_remote_command "rm /users/user/*.output 2>/dev/null || true"
    
    local clientCommand="cd /users/user/protobuf/ghz-client/ && bash ./run_client_cloudlab.sh > ./ghz.output"
    export CONCURRENCY=1000
    exported_vars=$(capture_exported_vars)

    export TEST_LOAD=$(echo "$TEST_LOAD" | tr -d '[:space:]')
    export OVERLOAD_CONTROL=$(echo "$OVERLOAD_CONTROL" | tr -d '[:space:]')

    echo "Starting the DVFS recording script in the background..."
    nohup python3 "./cloudlab/scripts/host/record_dvfs.py" &

    execute_remote_command "${exported_vars} && ${clientCommand}"
}

run_experiment() {
    set_environment_vars "$@"
    run_python_script "./grpc-app/gen-msgraph.py"
    run_python_script "./cloudlab/scripts/gen_k8s_yaml.py"
    perform_remote_operations "$@"
    handle_file_naming_and_copying
}

handle_args_and_run() {
    local capacity=0
    local subcall="parallel"
    local skip_k8s=false

    while (( "$#" )); do
        case "$1" in
            -c|--capacity)
                capacity=$2
                shift 2
                ;;
            -s|--subcall)
                subcall=$2
                shift 2
                ;;
            --skip)
                skip_k8s=true
                shift
                ;;
            --debug)
                export DEBUG_INFO=true
                shift
                ;;
            *)
                echo "Unknown option: $1"
                return 1
                ;;
        esac
    done

    echo "capacity: $capacity"
    echo "subcall: $subcall"
    run_experiment $capacity $subcall $skip_k8s
}

main() {
    handle_args_and_run "$@"
}

main "$@"