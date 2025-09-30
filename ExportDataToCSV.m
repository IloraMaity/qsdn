% Get the simulation start time from mission definition
sim_start_time = startTime;
% Create a simple table of all node names for easier processing in Python
all_sat_names=[];
all_gs_names=[];
for i=1:numel(sat)
    all_sat_names=[all_sat_names;{sprintf('SAT %d', i)}];
end
for i=1:numel(gs)
    all_gs_names=[all_gs_names;{sprintf('OGS %d', i)}];
end

% all_sat_names = "sat" + string(1:numel(sat));
% all_gs_names = "gs" + string(1:numel(gs));
all_node_names = [all_sat_names ; all_gs_names];
node_table = table(all_node_names, 'VariableNames', {'NodeName'});
% all_node_names= {N.name}';
% node_table=table(all_node_names, 'VariableNames', {'NodeName'});

% Convert the access intervals to a more Python-friendly format
intervals_export = intervals;
% Convert the interval datetimes to %elapsed seconds from the simulation start time
intervals_export.StartTime = seconds(intervals_export.StartTime - sim_start_time);
intervals_export.EndTime = seconds(intervals_export.EndTime - sim_start_time);

% Save the key data to CSV files
writetable(node_table, 'mininet_nodes.csv');
writetable(intervals_export, 'mininet_access_intervals.csv');

disp('Data for Mininet has been exported to CSV files.');