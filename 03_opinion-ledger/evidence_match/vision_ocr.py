# -*- coding: utf-8 -*-
"""Apple Vision 한국어 OCR(선택, macOS 전용).

회신 공문 중 글자가 없는 스캔 PDF·이미지를 읽을 때 쓴다. 테서랙트는 스캔 공문의 한글을
자주 오독하는 데 비해 Vision은 문장 원형을 비교적 잘 보존한다. 줄은 위→아래, 왼→오 순으로 잇는다.
외부 서버·API 키를 쓰지 않는다(기기 안에서 처리). 필요 패키지: pyobjc-framework-Vision, pyobjc-framework-Quartz
"""
import Quartz
import Vision


def _ocr_cgimage(img, lang=("ko-KR", "en-US")):
    req = Vision.VNRecognizeTextRequest.alloc().init()
    req.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
    req.setRecognitionLanguages_(list(lang))
    req.setUsesLanguageCorrection_(True)
    handler = Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(img, None)
    ok, err = handler.performRequests_error_([req], None)
    if not ok:
        raise RuntimeError(err)
    lines = []
    for obs in req.results() or []:
        cand = obs.topCandidates_(1)
        if not cand:
            continue
        bb = obs.boundingBox()                     # 정규화 좌표, y는 아래가 0
        lines.append((1 - bb.origin.y - bb.size.height, bb.origin.x, cand[0].string()))
    lines.sort(key=lambda t: (round(t[0], 3), t[1]))
    return "\n".join(s for _, _, s in lines)


def ocr_image_file(path):
    url = Quartz.CFURLCreateFromFileSystemRepresentation(
        None, path.encode(), len(path.encode()), False)
    src = Quartz.CGImageSourceCreateWithURL(url, None)
    img = Quartz.CGImageSourceCreateImageAtIndex(src, 0, None)
    return _ocr_cgimage(img)


def ocr_pdf_file(path, dpi=300):
    import fitz
    doc = fitz.open(path)
    pages = []
    for i in range(doc.page_count):
        pm = doc[i].get_pixmap(dpi=dpi)
        provider = Quartz.CGDataProviderCreateWithData(None, pm.samples,
                                                       len(pm.samples), None)
        img = Quartz.CGImageCreate(pm.width, pm.height, 8, 8 * pm.n, pm.stride,
                                   Quartz.CGColorSpaceCreateDeviceRGB(),
                                   Quartz.kCGImageAlphaNoneSkipLast if pm.n == 4
                                   else Quartz.kCGBitmapByteOrderDefault,
                                   provider, None, False,
                                   Quartz.kCGRenderingIntentDefault)
        pages.append(_ocr_cgimage(img))
    doc.close()
    return "\n\n".join(pages)
