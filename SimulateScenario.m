clear;
% Define the simulation time window
startTime = datetime(2025, 07, 20, 13, 22, 15, 'TimeZone', 'UTC');
stopTime = startTime + hours(24);
sampleTime = 60*1; % seconds
sc = satelliteScenario(startTime, stopTime, sampleTime);

% Add a satellite to the scenario from a TLE file.

try
    sat = satellite(sc, 'telesat.tle', "Name","SAT 1");
    % Select a single satellite to analyze
    selectedIndex=randi([1,numel(sat)],1,1);
    sat = sat(selectedIndex);
    % sat(1).Name="SAT 1";
catch
    disp('Error: TLE file not found. Please provide your TLE file in the MATLAB path.');
    return;
end

% Define the two ground station locations
gs1Loc = "Hawthorne, California";
gs1Lat = 33.9164;
gs1Lon = -118.3541;

gs2Loc = "Redmond, Washington";
gs2Lat = 47.6740;
gs2Lon = -122.1215;

% Add the ground stations to the scenario
% A minimum elevation angle of 10 degrees is set to model a reliable link
% that is not obstructed by low-lying terrain.[6, 2]
gs1 = groundStation(sc, gs1Lat, gs1Lon, 'Name', 'OGS 1', 'MinElevationAngle', 30);
gs2 = groundStation(sc, gs2Lat, gs2Lon, 'Name', 'OGS 2', 'MinElevationAngle', 30);
gs=[gs1, gs2 ];
% Perform access analysis between the single satellite and the two ground stations.[2]
ac = access(sat, gs);

% Get the access intervals and display the table.[1]
intervals = accessIntervals(ac);

% Display the results
disp('Access Intervals for the selected LEO Satellite and Ground Stations:');
disp(intervals);
