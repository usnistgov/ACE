import numpy as np
import logging
import cv2

logger = logging.getLogger(__name__)


def get_operations(operations):
    s = ""
    for o in operations:
        s += o
        s += ". "
    return s


def annotate_frame(res, frame, classes, db):
    colors = [(255, 0, 0), (0, 255, 0), (0, 0, 255),
              (255, 255, 0), (128, 0, 255), (255, 128, 0)]
    data = res.data
    color_counter = 0
    for roi in data.roi:
        if roi.HasField("box"):  # within roi message, one of localization is BoundingBox
            box = roi.box
            if roi.classification not in classes:
                logger.debug("Adding '{!s}' to classification dict".format(
                    roi.classification))
                classes[roi.classification] = color_counter % len(colors)
                color_counter += 1
            display_text = "{!s} - {!s}".format(
                roi.classification, roi.confidence)
            cv2.rectangle(frame, (box.corner1.x, box.corner1.y), (box.corner2.x,
                                                                  box.corner2.y), colors[classes[roi.classification]], 2)
            cv2.putText(frame, display_text, (box.corner1.x, box.corner1.y),
                        cv2.FONT_HERSHEY_COMPLEX, 1, (255, 255, 0))
    return frame


def render(resp, window_names, classes, frame, db):
    for i, res in enumerate(resp.results):
        if res.frame.frame.ByteSize() > 0:
            frame = cv2.imdecode(np.fromstring(
                res.frame.frame.img, dtype=np.uint8), 1)
            logger.debug("Bytesize > 0, getting frame from response ", frame)

        window_name = "{!s}: {!s}".format(res.analytic.name, res.analytic.addr)
        if window_name not in window_names:
            cv2.namedWindow(window_name)
            window_names.append(window_name)
        frame = annotate_frame(res, frame, classes, db)
        cv2.imshow(window_name, frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break


def default_filter(frame):
    pass


default_filter_map = {
    "GaussianBlur": False,
    "MedianBlur": False,
    "BilateralBlur": False,
    "DegradeFactor": None,
    "CompressionFactor": 100,
    "ScaleFactor": None
}


class FrameFilter:
    def __init__(self, filter_map=default_filter_map):
        # TODO Update to include min/max values. JSON Schema?
        self.filters = default_filter_map

    def update(self, new_filters):
        # self.filters.update(new_filters)
        if new_filters.get("GaussianBlur"):
            self.filters["GaussianBlur"] = bool(new_filters.get("GaussianBlur").lower() == "true")
        if new_filters.get("MedianBlur"):
            self.filters["MedianBlur"] = bool(new_filters.get("MedianBlur").lower() == "true")
        if new_filters.get("BilateralBlur"):
            self.filters["BilateralBlur"] = bool(new_filters.get("BilateralBlur").lower() == "true")

        if new_filters.get("DegradeFactor"):
            self.filters["DegradeFactor"] = int(new_filters.get("DegradeFactor"))
            if self.filters["DegradeFactor"] <= 0:
                self.filters["DegradeFactor"] = None

        if new_filters.get("ScaleFactor"):
            self.filters["ScaleFactor"] = float(new_filters.get("ScaleFactor"))
            if self.filters["ScaleFactor"] <= 0:
                self.filters["ScaleFactor"] = None

        logger.info(self.filters)

    def filter(self, frame, handler):
        """Applies filters to the input frame and returns the filtered frame."""
        logger.info(self.filters)
        if self.filters.get("GaussianBlur"):
            self.filters["GaussianBlur"] = bool(self.filters.get("GaussianBlur"))
            if self.filters.get("GaussianBlur"):
                frame = cv2.GaussianBlur(frame, (15, 15), 0)
                handler.add_operation("Gaussian blur")
                handler.add_filter("GaussianBlur", self.filters.get("GaussianBlur"))
        if self.filters.get("MedianBlur"):
            self.filters["MedianBlur"] = bool(self.filters.get("MedianBlur"))
            if self.filters.get("MedianBlur"):
                frame = cv2.medianBlur(frame, 15)
                handler.add_operation("Median blur")
                handler.add_filter("MedianBlur", self.filters.get("MedianBlur"))
        if self.filters.get("BilateralBlur"):
            self.filters["BilateralBlur"] = bool(self.filters.get("BilateralBlur"))
            if self.filters.get("BilateralBlur"):
                frame = cv2.bilateralFilter(frame, 15, 75, 75)
                handler.add_operation("Bilateral blur")
                handler.add_filter("BilateralBlur", self.filters.get("BilateralBlur"))

        size = (frame.shape[1], frame.shape[0])
        if self.filters.get("DegradeFactor"):
            size_adj = (int(frame.shape[1]/int(self.filters.get("DegradeFactor"))), int(frame.shape[0]/int(self.filters.get("DegradeFactor"))))
            logger.info(size_adj)
            frame = cv2.resize(frame, size_adj)
            frame = cv2.resize(frame, size)
            handler.add_operation("Degraded through resizing by a factor of {!s}".format(self.filters.get("DegradeFactor")))
            handler.add_filter("DegradeFactor", self.filters.get("DegradeFactor"))
        if self.filters.get("ScaleFactor"):
            scale_adj = (int(frame.shape[1]*float(self.filters.get("ScaleFactor"))), int(frame.shape[0]*float(self.filters.get("ScaleFactor"))))
            frame = cv2.resize(frame, scale_adj)
            handler.add_operation("Resized by a factor of {!s}".format(self.filters.get("ScaleFactor")))
            handler.add_filter("ScaleFactor", self.filters.get("ScaleFactor"))

        encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), max(0, min(int(self.filters.get("CompressionFactor")), 100))]
        handler.add_operation("Compressed with JPEG quality level {!s}".format(self.filters.get("CompressionFactor")))

        return cv2.imencode(".jpeg", frame, encode_param)[1].tostring()
