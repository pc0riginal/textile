from datetime import datetime
from bson import ObjectId
from typing import Dict, List, Any
from app.database import get_collection

class InventoryService:
    """Service to handle inventory transfers and tracking"""
    
    async def create_transfer(self, company_id: str, transfer_data: Dict[str, Any], user_id: str) -> str:
        """
        Create an inventory transfer from source challan to multiple recipients
        
        Args:
            company_id: Company ID
            transfer_data: Transfer details including source_challan_id, recipients, etc.
            user_id: User creating the transfer
            
        Returns:
            Transfer ID
            
        Raises:
            ValueError: If validation fails
        """
        challans_collection = await get_collection("purchase_challans")
        transfers_collection = await get_collection("inventory_transfers")
        parties_collection = await get_collection("parties")
        
        # Get source challan
        source_challan = await challans_collection.find_one({
            "_id": ObjectId(transfer_data["source_challan_id"]),
            "company_id": ObjectId(company_id)
        })
        
        if not source_challan:
            raise ValueError("Source challan not found")
        
        # Validate available inventory
        total_boxes_to_transfer = sum(r["boxes"] for r in transfer_data["recipients"])
        total_meters_to_transfer = sum(r["meters"] for r in transfer_data["recipients"])
        
        if total_boxes_to_transfer > source_challan["available_boxes"]:
            raise ValueError(f"Insufficient boxes. Available: {source_challan['available_boxes']}, Required: {total_boxes_to_transfer}")
        
        if total_meters_to_transfer > source_challan["available_meters"]:
            raise ValueError(f"Insufficient meters. Available: {source_challan['available_meters']}, Required: {total_meters_to_transfer}")
        
        # Generate transfer number
        count = await transfers_collection.count_documents({"company_id": ObjectId(company_id)})
        transfer_no = f"TR{count + 1:04d}"
        
        # Create recipient challans
        updated_recipients = []
        for recipient in transfer_data["recipients"]:
            # Get recipient party details
            party = await parties_collection.find_one({"_id": ObjectId(recipient["party_id"])})
            if not party:
                raise ValueError(f"Recipient party not found: {recipient['party_id']}")
            
            # Create new challan for recipient
            recipient_challan_data = {
                "company_id": ObjectId(company_id),
                "challan_no": await self._generate_challan_number(company_id, "received"),
                "challan_date": transfer_data["transfer_date"],
                "supplier_id": ObjectId(recipient["party_id"]),
                "supplier_name": party["name"],
                "financial_year": source_challan["financial_year"],
                
                # Copy material details from source
                "items": [{
                    "quality": transfer_data["quality"],
                    "boxes": recipient["boxes"],
                    "meters_per_box": recipient["meters"] / recipient["boxes"] if recipient["boxes"] > 0 else 0,
                    "total_meters": recipient["meters"],
                    "weight": 0.0,
                    "rate_per_meter": source_challan["items"][0]["rate_per_meter"] if source_challan["items"] else 0,
                    "amount": recipient["meters"] * (source_challan["items"][0]["rate_per_meter"] if source_challan["items"] else 0)
                }],
                
                # No broker/transporter for transfers
                "broker_id": None,
                "brokerage": 0.0,
                "transporter_id": None,
                "freight": 0.0,
                
                # No taxes for transfers
                "taxable_amount": 0.0,
                "cgst": 0.0,
                "sgst": 0.0,
                "igst": 0.0,
                "tcs": 0.0,
                "tds": 0.0,
                "total_amount": 0.0,
                
                # Inventory tracking
                "total_boxes": recipient["boxes"],
                "total_meters": recipient["meters"],
                "available_boxes": recipient["boxes"],
                "available_meters": recipient["meters"],
                "transferred_boxes": 0,
                "transferred_meters": 0.0,
                
                # Mark as received via transfer
                "is_transfer_source": False,
                "is_received_via_transfer": True,
                "transfer_source_id": ObjectId(transfer_data["source_challan_id"]),
                "transfer_reference": transfer_no,
                
                "payment_terms": None,
                "notes": f"Received via transfer {transfer_no}",
                "attachments": [],
                "status": "finalized",
                "created_by": ObjectId(user_id),
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
                "audit_log": [{
                    "action": "created_via_transfer",
                    "user_id": ObjectId(user_id),
                    "timestamp": datetime.utcnow(),
                    "changes": {"transfer_no": transfer_no}
                }]
            }
            
            # Insert recipient challan
            result = await challans_collection.insert_one(recipient_challan_data)
            
            # Update recipient info with created challan details
            recipient_updated = recipient.copy()
            recipient_updated["created_challan_id"] = result.inserted_id
            recipient_updated["created_challan_no"] = recipient_challan_data["challan_no"]
            updated_recipients.append(recipient_updated)
        
        # Create transfer record
        transfer_record = {
            "company_id": ObjectId(company_id),
            "transfer_no": transfer_no,
            "transfer_date": transfer_data["transfer_date"],
            
            # Source details
            "source_challan_id": ObjectId(transfer_data["source_challan_id"]),
            "source_challan_no": source_challan["challan_no"],
            "source_party_id": source_challan["supplier_id"],
            "source_party_name": source_challan["supplier_name"],
            
            # Transfer details
            "quality": transfer_data["quality"],
            "boxes_transferred": total_boxes_to_transfer,
            "meters_transferred": total_meters_to_transfer,
            
            # Recipients
            "recipients": updated_recipients,
            
            "reason": transfer_data.get("reason"),
            "notes": transfer_data.get("notes"),
            "status": "completed",
            
            "created_by": ObjectId(user_id),
            "created_at": datetime.utcnow(),
            
            # Reversal tracking
            "is_reversed": False,
            "reversed_at": None,
            "reversed_by": None
        }
        
        transfer_result = await transfers_collection.insert_one(transfer_record)
        
        # Update source challan inventory
        await challans_collection.update_one(
            {"_id": ObjectId(transfer_data["source_challan_id"])},
            {
                "$inc": {
                    "available_boxes": -total_boxes_to_transfer,
                    "available_meters": -total_meters_to_transfer,
                    "transferred_boxes": total_boxes_to_transfer,
                    "transferred_meters": total_meters_to_transfer
                },
                "$set": {
                    "is_transfer_source": True,
                    "updated_at": datetime.utcnow()
                },
                "$push": {
                    "audit_log": {
                        "action": "inventory_transferred",
                        "user_id": ObjectId(user_id),
                        "timestamp": datetime.utcnow(),
                        "changes": {
                            "transfer_no": transfer_no,
                            "boxes_transferred": total_boxes_to_transfer,
                            "meters_transferred": total_meters_to_transfer
                        }
                    }
                }
            }
        )
        
        return str(transfer_result.inserted_id)
    
    async def _generate_challan_number(self, company_id: str, prefix: str = "CH") -> str:
        """Generate unique challan number"""
        challans_collection = await get_collection("purchase_challans")
        count = await challans_collection.count_documents({"company_id": ObjectId(company_id)})
        return f"{prefix.upper()}{count + 1:04d}"
    
    async def get_available_inventory(self, company_id: str, challan_id: str = None) -> List[Dict]:
        """Get available inventory for transfers"""
        challans_collection = await get_collection("purchase_challans")
        
        filter_query = {
            "company_id": ObjectId(company_id),
            "available_boxes": {"$gt": 0},
            "status": "finalized"
        }
        
        if challan_id:
            filter_query["_id"] = ObjectId(challan_id)
        
        challans = await challans_collection.find(filter_query).sort("challan_date", -1).to_list(None)
        
        # Convert ObjectIds to strings for JSON serialization
        for challan in challans:
            challan["id"] = str(challan["_id"])
            challan["company_id"] = str(challan["company_id"])
            challan["supplier_id"] = str(challan["supplier_id"])
        
        return challans
    
    async def reverse_transfer(self, transfer_id: str, user_id: str) -> bool:
        """Reverse an inventory transfer"""
        transfers_collection = await get_collection("inventory_transfers")
        challans_collection = await get_collection("purchase_challans")
        
        # Get transfer record
        transfer = await transfers_collection.find_one({"_id": ObjectId(transfer_id)})
        if not transfer or transfer["is_reversed"]:
            raise ValueError("Transfer not found or already reversed")
        
        # Reverse inventory in source challan
        await challans_collection.update_one(
            {"_id": transfer["source_challan_id"]},
            {
                "$inc": {
                    "available_boxes": transfer["boxes_transferred"],
                    "available_meters": transfer["meters_transferred"],
                    "transferred_boxes": -transfer["boxes_transferred"],
                    "transferred_meters": -transfer["meters_transferred"]
                },
                "$push": {
                    "audit_log": {
                        "action": "transfer_reversed",
                        "user_id": ObjectId(user_id),
                        "timestamp": datetime.utcnow(),
                        "changes": {"transfer_no": transfer["transfer_no"]}
                    }
                }
            }
        )
        
        # Delete recipient challans
        for recipient in transfer["recipients"]:
            if recipient.get("created_challan_id"):
                await challans_collection.delete_one({"_id": ObjectId(recipient["created_challan_id"])})
        
        # Mark transfer as reversed
        await transfers_collection.update_one(
            {"_id": ObjectId(transfer_id)},
            {
                "$set": {
                    "is_reversed": True,
                    "reversed_at": datetime.utcnow(),
                    "reversed_by": ObjectId(user_id),
                    "status": "cancelled"
                }
            }
        )
        
        return True