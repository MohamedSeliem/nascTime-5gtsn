#!/bin/bash
# development helper: opp_run with the m2s72.sh paths; args passed through; cwd simulations/m2
N=/root/inv/nascTime-5gtsn
source /root/stack/omnetpp-6.4.0/setenv -f >/dev/null
cd $N/simulations/m2 && exec opp_run -l $N/src/nasctime/m2/nasctime_m2 -l /root/stack/simu5g-1.8.0/src/simu5g \
  -n $N/simulations:$N/src:/root/stack/simu5g-1.8.0/src:/root/stack/inet-4.7.0/src -x nasctime.nodes -u Cmdenv "$@"
