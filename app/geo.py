# Shapely polygon filtering — build order step 3

from shapely.geometry import Point, Polygon

def filter_by_polygon(jobs, polygon_coordinates):
    job_list = []
    polygon = Polygon(polygon_coordinates)
    for job in jobs:
        if job["latitude"] is None or job["longitude"] is None:
            continue
        point = Point(job["longitude"], job["latitude"])
        if polygon.contains(point) == True:
            job_list.append(job)
    return job_list


if __name__ == "__main__":
    ### Testable Code - Succesful ###
    test_polygon = [
        (-122.80, 45.45),
        (-122.80, 45.55),
        (-122.60, 45.55),
        (-122.60, 45.45),
    ]

    test_jobs = [
        {"title": "Inside Job 1", "latitude": 45.50, "longitude": -122.67},
        {"title": "Inside Job 2", "latitude": 45.48, "longitude": -122.65},
        {"title": "Outside Job (Seattle)", "latitude": 47.60, "longitude": -122.33},
        {"title": "Missing Coords Job", "latitude": None, "longitude": None},
    ]

    results = filter_by_polygon(test_jobs, test_polygon)
    print(f"{len(results)} of {len(test_jobs)} jobs matched:")
    for job in results:
        print(" -", job["title"])
