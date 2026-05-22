def classFactory(iface):
    from .streetview_qgis_cej_plus import StreetViewQGISCej
    return StreetViewQGISCej(iface)